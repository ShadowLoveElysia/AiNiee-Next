"""On-demand media dependencies and public model preparation; no base imports."""

import argparse
import importlib
import importlib.util
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import venv

from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS, get_model

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / "Resource/MediaRuntime"
PACKAGES = ("torch", "torchaudio", "transformers", "accelerate", "funasr", "sentencepiece",
            "silero_vad", "onnxruntime", "soundcard", "numpy", "soundfile", "librosa",
            "huggingface_hub", "safetensors")
MODELS = {
    "sensevoice": ("iic/SenseVoiceSmall", "7bf452403abd7353a300cd760f7adae7701c92c1"),
    "index": ("IndexTeam/Index-Translate-2B", "3473f22736a89e12ece274e2130be2d5898dbda3"),
    "hymt": ("Tencent-Hunyuan/Hy-MT2-1.8B", "09fd81b4d8952bad2906e5c72f167bc84b0c6921"),
    "index-9b": ("IndexTeam/Index-Translate-9B", "6ae85e9af278d70007d869d21c263d7d00c3d8dc"),
    "hymt-7b": ("Tencent-Hunyuan/Hy-MT2-7B", "e4352246d81541283e5b27590c9ca2833ac6ca06"),
    "index-q4": ("IndexTeam/Index-Translate-2B-GGUF", "b92a7c7bf499a6f05da1a66fab8549da3de5b603"),
    "index-q6": ("IndexTeam/Index-Translate-2B-GGUF", "b92a7c7bf499a6f05da1a66fab8549da3de5b603"),
    "hymt-q4": ("Tencent-Hunyuan/Hy-MT2-1.8B-GGUF", "e97e6af0ec0950385644d7c0a8e5c899071f722b"),
    "hymt-q6": ("Tencent-Hunyuan/Hy-MT2-1.8B-GGUF", "e97e6af0ec0950385644d7c0a8e5c899071f722b"),
}


def required_packages(device: str = "cpu") -> tuple[str, ...]:
    return PACKAGES + (("mlx", "mlx_lm") if device == "mlx" else ())


def needs_install(device: str) -> bool:
    if any(importlib.util.find_spec(name) is None for name in required_packages(device)):
        return True
    minimums = {"torch": (2, 9, 1), "torchaudio": (2, 9, 1),
                "transformers": (5, 7, 0) if sys.platform == "darwin" else (5, 6, 0)}
    if device == "mlx":
        minimums.update({"mlx": (0, 32, 3), "mlx-lm": (0, 32, 0)})
    for name, minimum in minimums.items():
        try:
            version = importlib.metadata.version(name).split('+')[0]
            if tuple(int(part) for part in version.split('.')[:3]) < minimum:
                return True
        except (importlib.metadata.PackageNotFoundError, ValueError):
            return True
    return False


def runtime_python() -> Path:
    if sys.platform == "darwin":
        return RUNTIME_ROOT / ("macos-" + platform.machine().lower()) / "bin/python"
    return RUNTIME_ROOT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def selected_python(saved="") -> str:
    if saved and Path(saved).is_file():
        return saved
    if runtime_python().is_file():
        return str(runtime_python())
    return sys.executable


def subprocess_environment() -> dict:
    environment = os.environ.copy()
    # A TUI launched through uv/another interpreter may carry incompatible paths.
    for name in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(name, None)
    environment["PYTHONUTF8"] = "1"
    return environment


def audio_interpreters(preferred: str) -> list[str]:
    candidates = [preferred, str(runtime_python()), sys.executable]
    if os.name == "nt":
        candidates.append(str(ROOT / ".venv-win/Scripts/python.exe"))
    result = []
    seen = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen and Path(candidate).is_file():
            seen.add(key)
            result.append(candidate)
    return result


def discover_audio_runtime(preferred: str) -> tuple[str, list[str]]:
    last_error = None
    for interpreter in audio_interpreters(preferred):
        try:
            return interpreter, discover_devices(interpreter)
        except (RuntimeError, OSError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("AudioRuntimePythonMissing")


class AudioDeviceProbeTimeout(RuntimeError):
    """Enumeration deadline expired; this does not imply a broken audio device."""


def discover_devices(interpreter: str) -> list[str]:
    # Device listing needs only SoundCard, not the project runtime/model catalog.
    listing = "sc.all_microphones(include_loopback=False)" if sys.platform == "darwin" else "sc.all_speakers()"
    script = "import json; import soundcard as sc; print(json.dumps({'speakers': [s.name for s in " + listing + "]}), flush=True)"
    try:
        result = subprocess.run(
            [interpreter, "-u", "-c", script], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            env=subprocess_environment(),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise AudioDeviceProbeTimeout("Audio device detection timed out after 60 seconds") from None
    lines = result.stdout.splitlines()
    try:
        report = json.loads(lines[-1]) if lines else {}
    except ValueError:
        report = {}
    if result.returncode:
        # Report bounded diagnostic categories, never arbitrary stderr/config.
        detail = report.get("error_type", "")
        if "No module named 'soundcard'" in result.stderr:
            detail = "soundcard missing"
        elif "No module named" in result.stderr:
            detail = "runtime module missing"
        raise RuntimeError(f"AudioDeviceProbeFailed (exit={result.returncode}, {detail or 'runtime error'})")
    speakers = report.get("speakers")
    if not isinstance(speakers, list) or not all(isinstance(name, str) for name in speakers):
        raise RuntimeError("AudioDeviceProbeInvalidResponse")
    if sys.platform == "darwin":
        from ModuleFolders.Media.macos_audio import SYSTEM_AUDIO, SCREEN_AUDIO, supported
        if supported():
            speakers = [SYSTEM_AUDIO, SCREEN_AUDIO, *speakers]
    if not speakers:
        raise RuntimeError("NoAudioOutputDevices")
    return speakers


def probe(interpreter: str, device: str, family: str = "index") -> dict:
    result = subprocess.run(
        [interpreter, "-m", "ModuleFolders.Media.runtime", "probe", "--device", device, "--family", family], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        env=subprocess_environment(),
        stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RuntimeError(f"Runtime check exited: {result.returncode}")
    report = json.loads(result.stdout.splitlines()[-1])
    report["ready"] = not report["missing"] and not report.get("compute_error")
    return report


def install(device: str, *, translation_device: str = "") -> None:
    if translation_device == "mlx" and (sys.platform != "darwin" or platform.machine().lower() not in {"arm64", "aarch64"}):
        raise RuntimeError("MLX requires native arm64 macOS Python")
    if translation_device == "mlx" and platform.mac_ver()[0] and int(platform.mac_ver()[0].split('.')[0]) < 14:
        raise RuntimeError("MLX 0.32 requires macOS 14 or newer")
    if sys.platform == "darwin" and platform.machine().lower() != "arm64":
        raise RuntimeError("Automatic macOS inference setup requires Apple Silicon with native arm64 Python; current Torch wheels do not support Intel macOS")
    uv = shutil.which("uv")
    destination = runtime_python().parent.parent
    if not runtime_python().is_file():
        print("Creating isolated media runtime", flush=True)
        if uv:
            subprocess.run([uv, "venv", "--python", sys.executable if sys.platform == "darwin" else "3.12",
                            "--seed", str(destination)], check=True)
        elif getattr(sys, "frozen", False):
            raise RuntimeError("A Python 3.12 interpreter or uv is required to install the media runtime")
        else:
            venv.EnvBuilder(with_pip=True).create(destination)
    python = str(runtime_python())
    installer = [uv, "pip", "install", "--python", python] if uv else [python, "-m", "pip", "install"]
    torch_index = "https://download.pytorch.org/whl/cu126" if device.startswith("cuda") else "https://download.pytorch.org/whl/cpu"
    suffix = "+cu126" if device.startswith("cuda") else ("" if sys.platform == "darwin" else "+cpu")
    if sys.platform == "darwin":
        torch_index = "https://pypi.org/simple"
    torch_packages = ["torch==2.9.1" + suffix, "torchaudio==2.9.1" + suffix]
    subprocess.run([*installer, "--index-url", torch_index, *torch_packages], check=True)
    apple_packages = ["mlx==0.32.3", "mlx-lm==0.32.0"] if translation_device == "mlx" else []
    transformers = "transformers==5.7.0" if sys.platform == "darwin" else "transformers==5.6.0"
    subprocess.run([*installer, "--extra-index-url", torch_index, *torch_packages, transformers, "accelerate", "funasr>=1.2,<2", "sentencepiece",
                    "silero-vad", "onnxruntime", "soundcard", "numpy", "soundfile", "librosa",
                    "huggingface-hub", "safetensors", *apple_packages], check=True)
    print(json.dumps({"runtime_python": python}), flush=True)


def download(root: Path, family: str) -> None:
    from ModuleFolders.Media.modelscope_download import download_model

    model = get_model(family)
    for key in ("sensevoice", model.key):
        repo, revision = MODELS[key]
        target = root / ("SenseVoiceSmall" if key == "sensevoice" else model.directory)
        filename = model.filename if key != "sensevoice" and model.backend == "gguf" else ""
        download_model(repo, revision, target, filename=filename)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("probe", "devices", "install", "configure", "download"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--family", choices=tuple(model.key for model in TRANSLATION_MODELS), default="index")
    parser.add_argument("--managed", action="store_true")
    args = parser.parse_args()
    if args.managed:
        from ModuleFolders.Media.supervisor import start_core_watchdog
        def parent_gone():
            if os.name == "nt":
                subprocess.Popen(["taskkill", "/PID", str(os.getpid()), "/T", "/F"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.killpg(os.getpgrp(), signal.SIGTERM)
            os._exit(1)
        start_core_watchdog(parent_gone)
    if args.action == "probe":
        missing = [name for name in PACKAGES if importlib.util.find_spec(name) is None]
        cuda, gpu, mps = False, "", False
        versions = {}
        if "torch" not in missing:
            try:
                import torch
                versions["torch"] = torch.__version__
                cuda = torch.cuda.is_available()
                mps = torch.backends.mps.is_available()
                if cuda:
                    gpu = torch.cuda.get_device_name(0)
            except Exception:
                missing.append("torch")
        for name in ("torchaudio", "transformers", "onnxruntime"):
            if name not in missing:
                try:
                    module = importlib.import_module(name)
                    versions[name] = module.__version__
                    if name == "transformers":
                        major, minor = (int(part) for part in module.__version__.split('.')[:2])
                        minimum = (5, 7) if sys.platform == "darwin" else (5, 6)
                        if (major, minor) < minimum:
                            missing.append("transformers>=" + '.'.join(map(str, minimum)))
                except Exception:
                    missing.append(name)
        from ModuleFolders.Media.compute import detect_adapters, select_compute
        adapters = detect_adapters()
        checkpoint = get_model(args.family)
        compute_error = ""
        compute = {}
        try:
            compute = select_compute(args.device, gguf=checkpoint.backend == "gguf", cuda_available=cuda, adapters=adapters,
                                     mlx_compatible=checkpoint.family == "index", mps_available=mps)
            if compute["translation_device"] == "mlx":
                for name, minimum in (("mlx", (0, 32, 3)), ("mlx_lm", (0, 32, 0))):
                    if importlib.util.find_spec(name) is None:
                        missing.append(name)
                        continue
                    try:
                        module = importlib.import_module(name)
                        version = importlib.metadata.version(name.replace('_', '-'))
                        versions[name] = version
                        if tuple(int(part) for part in version.split('.')[:3]) < minimum:
                            missing.append(name + ">=" + '.'.join(map(str, minimum)))
                    except Exception:
                        missing.append(name)
                if "mlx" not in missing:
                    import mlx.core as mx
                    if not mx.metal.is_available():
                        raise RuntimeError("MLX Metal GPU is unavailable")
            if sys.platform == "darwin":
                gpu = adapters[0]["name"] if adapters else ""
            if checkpoint.backend == "gguf":
                from ModuleFolders.Media.gguf_runtime import find_server
                if find_server(compute["llama_backend"]) is None:
                    missing.append("llama.cpp " + compute["llama_backend"])
        except RuntimeError as exc:
            compute_error = str(exc)
        print(json.dumps({"python": sys.executable, "version": sys.version.split()[0], "missing": missing,
                          "cuda": cuda, "gpu": gpu, "versions": versions, "adapters": adapters,
                          "mps": mps, "platform": sys.platform, "architecture": platform.machine(),
                          "compute": compute, "compute_error": compute_error}), flush=True)
    elif args.action == "devices":
        import soundcard as sc
        from ModuleFolders.Media.audio_capture import devices
        names = [device.name for device in devices(sc)]
        if sys.platform == "darwin":
            from ModuleFolders.Media.macos_audio import SYSTEM_AUDIO, SCREEN_AUDIO, supported
            if supported():
                names = [SYSTEM_AUDIO, SCREEN_AUDIO, *names]
        print(json.dumps({"speakers": names}), flush=True)
    elif args.action in {"install", "configure"}:
        from ModuleFolders.Media.compute import detect_adapters, select_compute
        adapters = detect_adapters()
        cuda_possible = any(adapter["vendor"] == "nvidia" for adapter in adapters)
        if args.device == "cuda:0":
            cuda_possible = True
        compute = select_compute(args.device, gguf=get_model(args.family).backend == "gguf",
                                 cuda_available=cuda_possible, adapters=adapters,
                                 mlx_compatible=get_model(args.family).family == "index")
        if args.action == "install" or needs_install(compute["translation_device"]):
            install(compute["asr_device"], translation_device=compute["translation_device"])
        else:
            print(json.dumps({"runtime_python": sys.executable}), flush=True)
        if args.action == "configure" and get_model(args.family).backend == "gguf":
            from ModuleFolders.Media.gguf_runtime import prepare
            prepare(lambda value: print(value, flush=True), backend=compute["llama_backend"])
        if args.action == "configure" and sys.platform == "darwin":
            from ModuleFolders.Media.macos_audio import prepare_helper
            try:
                prepare_helper(lambda value: print(value, flush=True))
            except RuntimeError as exc:
                print(json.dumps({"error_detail": str(exc)[:1600]}), flush=True)
                raise
    else:
        if args.model_root is None:
            parser.error("--model-root is required")
        download(args.model_root, args.family)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
