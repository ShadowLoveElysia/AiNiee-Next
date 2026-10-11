"""On-demand media dependencies and public model preparation; no base imports."""

import argparse
import importlib
import importlib.util
import json
import os
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
    "sensevoice": ("FunAudioLLM/SenseVoiceSmall", "3847d57b6bdf2dd8875cb1508d2af43d80a16bf7"),
    "index": ("IndexTeam/Index-Translate-2B", "a516854233b170140b57d36b48d7148c0edebabb"),
    "hymt": ("tencent/Hy-MT2-1.8B", "9a341cd1b679d3efd23b46e847b01745a71ed792"),
}
MODELS.update({model.key: (model.repo, model.revision) for model in TRANSLATION_MODELS})


def runtime_python() -> Path:
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
    script = "import json; import soundcard as sc; print(json.dumps({'speakers': [s.name for s in sc.all_speakers()]}), flush=True)"
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


def install(device: str) -> None:
    uv = shutil.which("uv")
    if not runtime_python().is_file():
        print("Creating isolated media runtime", flush=True)
        if uv:
            subprocess.run([uv, "venv", "--python", "3.12", "--seed", str(RUNTIME_ROOT)], check=True)
        elif getattr(sys, "frozen", False):
            raise RuntimeError("A Python 3.12 interpreter or uv is required to install the media runtime")
        else:
            venv.EnvBuilder(with_pip=True).create(RUNTIME_ROOT)
    python = str(runtime_python())
    installer = [uv, "pip", "install", "--python", python] if uv else [python, "-m", "pip", "install"]
    torch_index = "https://download.pytorch.org/whl/cu126" if device.startswith("cuda") else "https://download.pytorch.org/whl/cpu"
    suffix = "+cu126" if device.startswith("cuda") else ("" if sys.platform == "darwin" else "+cpu")
    if sys.platform == "darwin":
        torch_index = "https://pypi.org/simple"
    torch_packages = ["torch==2.9.1" + suffix, "torchaudio==2.9.1" + suffix]
    subprocess.run([*installer, "--index-url", torch_index, *torch_packages], check=True)
    subprocess.run([*installer, "--extra-index-url", torch_index, *torch_packages, "transformers==5.6.0", "accelerate", "funasr>=1.2,<2", "sentencepiece",
                    "silero-vad", "onnxruntime", "soundcard", "numpy", "soundfile", "librosa",
                    "huggingface-hub", "safetensors"], check=True)
    print(json.dumps({"runtime_python": python}), flush=True)


def download(root: Path, family: str) -> None:
    import hashlib
    from huggingface_hub import HfApi, snapshot_download

    family = get_model(family).key
    api = HfApi(token=False)
    for key in ("sensevoice", family):
        repo, revision = MODELS[key]
        info = api.model_info(repo, revision=revision, files_metadata=True)
        files = [f for f in info.siblings if "/" not in f.rfilename and not f.rfilename.startswith(".")
                 and (f.rfilename.endswith((".safetensors", ".json", ".txt", ".yaml", ".jinja", ".model", ".pt", ".mvn"))
                      or f.rfilename.startswith("README"))]
        if key != "sensevoice" and get_model(family).backend == "gguf":
            files = [f for f in info.siblings if f.rfilename == get_model(family).filename]
        target = root / repo.split("/")[-1]
        print(json.dumps({"model": repo, "stage": "download", "bytes": sum(f.size or 0 for f in files)}), flush=True)
        snapshot_download(repo, revision=revision, local_dir=target, token=False,
                          allow_patterns=[f.rfilename for f in files], max_workers=3)
        for item in files:
            path = target / item.rfilename
            if path.stat().st_size != item.size:
                raise RuntimeError("Model size verification failed")
            digest = hashlib.sha256() if item.lfs else hashlib.sha1()
            if not item.lfs:
                digest.update(f"blob {item.size}\0".encode())
            with path.open("rb") as stream:
                for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(data)
            expected = item.lfs.sha256 if item.lfs else item.blob_id
            if digest.hexdigest() != expected:
                raise RuntimeError("Model checksum verification failed")
        (target / "MODEL_INFO.json").write_text(json.dumps({"repo": repo, "revision": revision,
                                                          "status": "verified"}, indent=2), encoding="utf-8")
        print(json.dumps({"model": repo, "status": "verified"}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("probe", "devices", "install", "configure", "download"))
    parser.add_argument("--device", default="cpu")
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
        cuda, gpu = False, ""
        versions = {}
        if "torch" not in missing:
            try:
                import torch
                versions["torch"] = torch.__version__
                cuda = torch.cuda.is_available()
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
                        if (major, minor) < (5, 6):
                            missing.append("transformers>=5.6")
                except Exception:
                    missing.append(name)
        from ModuleFolders.Media.compute import detect_adapters, select_compute
        adapters = detect_adapters()
        checkpoint = get_model(args.family)
        compute_error = ""
        compute = {}
        try:
            compute = select_compute(args.device, gguf=checkpoint.backend == "gguf", cuda_available=cuda, adapters=adapters)
            if checkpoint.backend == "gguf":
                from ModuleFolders.Media.gguf_runtime import find_server
                if find_server(compute["llama_backend"]) is None:
                    missing.append("llama.cpp " + compute["llama_backend"])
        except RuntimeError as exc:
            compute_error = str(exc)
        print(json.dumps({"python": sys.executable, "version": sys.version.split()[0], "missing": missing,
                          "cuda": cuda, "gpu": gpu, "versions": versions, "adapters": adapters,
                          "compute": compute, "compute_error": compute_error}), flush=True)
    elif args.action == "devices":
        import soundcard as sc
        print(json.dumps({"speakers": [speaker.name for speaker in sc.all_speakers()]}), flush=True)
    elif args.action in {"install", "configure"}:
        from ModuleFolders.Media.compute import detect_adapters, select_compute
        adapters = detect_adapters()
        cuda_possible = any(adapter["vendor"] == "nvidia" for adapter in adapters)
        if args.device == "cuda:0":
            cuda_possible = True
        compute = select_compute(args.device, gguf=get_model(args.family).backend == "gguf",
                                 cuda_available=cuda_possible, adapters=adapters)
        if args.action == "install" or any(importlib.util.find_spec(name) is None for name in PACKAGES):
            install(compute["asr_device"])
        else:
            print(json.dumps({"runtime_python": sys.executable}), flush=True)
        if args.action == "configure" and get_model(args.family).backend == "gguf":
            from ModuleFolders.Media.gguf_runtime import prepare
            prepare(lambda value: print(value, flush=True), backend=compute["llama_backend"])
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
