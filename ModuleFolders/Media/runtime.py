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


def torch_runtime_info(interpreter=None, *, check_execution=False):
    """Release native DLLs by completing discovery in a short-lived child."""
    python = str(interpreter or sys.executable)
    script = ("import json,torch; info={'version':torch.version.cuda,'available':torch.cuda.is_available()}; "
              "info.update({'name':torch.cuda.get_device_name(0),'capability':list(torch.cuda.get_device_capability(0))}) "
              "if info['available'] else None; ")
    if check_execution:
        script += "from ModuleFolders.Media.runtime import cuda_execution_check; info['check']=cuda_execution_check(torch); "
    script += "print(json.dumps(info))"
    result = subprocess.run([python, '-c', script], capture_output=True, text=True, timeout=45,
                            cwd=ROOT, env=subprocess_environment(), stdin=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError(f'Torch discovery/check exited: {result.returncode}')
    return json.loads(result.stdout.splitlines()[-1])


def cuda_install_build(adapters=None, *, interpreter=None) -> str:
    from ModuleFolders.Media.compute import detect_adapters, select_cuda_build
    override = os.environ.get("AINIEE_MEDIA_CUDA_BUILD", "")
    if override:
        if override not in {"cu126", "cu128"}:
            raise ValueError("AINIEE_MEDIA_CUDA_BUILD must be cu126 or cu128")
        return override
    info = {}
    try:
        info = torch_runtime_info(interpreter)
    except (OSError, RuntimeError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    version = info.get("version")
    build = "cu" + version.replace('.', '') if version else ""
    selected = ({"name": info.get("name", ""), "vendor": "nvidia", "compute_capability": info["capability"]}
                if info.get("available") and info.get("capability") else None)
    if adapters is None:
        adapters = [] if selected else detect_adapters()
    return select_cuda_build(adapters, installed_build=build, selected_adapter=selected)


def needs_install(device: str, *, recognizer='sensevoice') -> bool:
    if any(importlib.util.find_spec(name) is None for name in required_packages(device)):
        return True
    minimums = {"torch": (2, 9, 1), "torchaudio": (2, 9, 1),
                "transformers": (5, 7, 0) if sys.platform == "darwin" else (5, 6, 0)}
    try:
        torch_version = importlib.metadata.version('torch')
        audio_version = importlib.metadata.version('torchaudio')
        if torch_version.split('+')[0] != audio_version.split('+')[0]:
            return True
    except importlib.metadata.PackageNotFoundError:
        return True
    if device == "mlx":
        minimums.update({"mlx": (0, 32, 3), "mlx-lm": (0, 32, 0)})
    for name, minimum in minimums.items():
        try:
            version = importlib.metadata.version(name).split('+')[0]
            if tuple(int(part) for part in version.split('.')[:3]) < minimum:
                return True
        except (importlib.metadata.PackageNotFoundError, ValueError):
            return True
    if device.startswith("cuda"):
        try:
            info = torch_runtime_info(check_execution=True)
            build = cuda_install_build()
            if info['version'] != {"cu126": "12.6", "cu128": "12.8"}[build]:
                return True
        except Exception:
            return True
    return False


def cuda_execution_check(torch) -> dict:
    capability = torch.cuda.get_device_capability(0)
    version = torch.version.cuda or ""
    if capability[0] >= 10 and (not version or tuple(map(int, version.split('.')[:2])) < (12, 8)):
        raise RuntimeError("Blackwell GPU requires a CUDA 12.8+ PyTorch build; rerun prepare_media.bat to replace cu126")
    if capability[0] < 7 and version and tuple(map(int, version.split('.')[:2])) >= (12, 8):
        raise RuntimeError("Maxwell/Pascal GPU requires the cu126 build; rerun prepare_media.bat to replace cu128")
    import re
    arches = torch.cuda.get_arch_list()
    compatible = False
    for arch in arches:
        match = re.fullmatch(r"(sm|compute)_(\d+)", arch)
        if not match:
            continue
        number = int(match[2])
        compiled = (number // 10, number % 10)
        if (match[1] == "sm" and compiled[0] == capability[0] and compiled[1] <= capability[1]) or (
                match[1] == "compute" and compiled <= capability):
            compatible = True
    if arches and not compatible:
        raise RuntimeError(f"PyTorch build does not include compatible kernels for sm_{capability[0]}{capability[1]}; rerun prepare_media.bat with the GPU-appropriate build")
    try:
        # Device discovery alone succeeds even when this wheel lacks GPU kernels.
        value = torch.ones((16, 16), device="cuda:0")
        result = (value @ value).sum().item()
        torch.cuda.synchronize()
        if result != 4096:
            raise RuntimeError("Unexpected CUDA result")
    except Exception as exc:
        raise RuntimeError("CUDA execution check failed: " + str(exc)[:500] + "; update the NVIDIA driver and rerun prepare_media.bat") from None
    return {"capability": list(capability), "cuda_version": version, "compiled_arches": arches}


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


def probe(interpreter: str, device: str, family: str = "index", *, recognizer='sensevoice', asr_device='auto', asr_endpoint='http://127.0.0.1:8001/v1') -> dict:
    recognition_args = ["--recognizer", recognizer, "--asr-device", asr_device] if recognizer != 'sensevoice' or asr_device != 'auto' else []
    if asr_endpoint != 'http://127.0.0.1:8001/v1':
        recognition_args += ['--asr-endpoint', asr_endpoint]
    result = subprocess.run(
        [interpreter, "-m", "ModuleFolders.Media.runtime", "probe", "--device", device, "--family", family, *recognition_args], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        env=subprocess_environment(),
        stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RuntimeError(f"Runtime check exited: {result.returncode}")
    report = json.loads(result.stdout.splitlines()[-1])
    report["ready"] = not report["missing"] and not report.get("compute_error")
    return report


def install(device: str, *, translation_device: str = "", recognizer='sensevoice') -> None:
    os.environ['UV_NO_PROGRESS'] = 'false'
    if translation_device == "mlx" and (sys.platform != "darwin" or platform.machine().lower() not in {"arm64", "aarch64"}):
        raise RuntimeError("MLX requires native arm64 macOS Python")
    if translation_device == "mlx" and platform.mac_ver()[0] and int(platform.mac_ver()[0].split('.')[0]) < 14:
        raise RuntimeError("MLX 0.32 requires macOS 14 or newer")
    if sys.platform == "darwin" and platform.machine().lower() != "arm64":
        raise RuntimeError("Automatic macOS inference setup requires Apple Silicon with native arm64 Python; current Torch wheels do not support Intel macOS")
    uv = shutil.which("uv")
    from ModuleFolders.Media.package_sources import package_indexes
    seed_indexes = package_indexes("cpu")
    destination = runtime_python().parent.parent
    if not runtime_python().is_file():
        print("Creating isolated media runtime", flush=True)
        if uv:
            subprocess.run([uv, "venv", "--python", sys.executable if sys.platform == "darwin" else "3.12",
                            "--seed", "--index-url", seed_indexes["pypi"], "--allow-existing", str(destination)], check=True)
        elif getattr(sys, "frozen", False):
            raise RuntimeError("A Python 3.12 interpreter or uv is required to install the media runtime")
        else:
            venv.EnvBuilder(with_pip=True).create(destination)
    python = str(runtime_python())
    installer = [uv, "pip", "install", "--python", python] if uv else [python, "-m", "pip", "install"]
    build = cuda_install_build(interpreter=python) if device.startswith("cuda") else "cpu"
    indexes = package_indexes(build)
    torch_index = indexes["torch"]
    suffix = "+" + build if sys.platform != "darwin" else ""
    print(json.dumps({"package_source": indexes["source"], "torch_index": torch_index, "pypi_index": indexes["pypi"]}), flush=True)
    torch_packages = ["torch==2.9.1" + suffix, "torchaudio==2.9.1" + suffix]
    if uv:
        subprocess.run([sys.executable, '-u', '-m', 'ModuleFolders.Media.package_download', '--python', python,
                        '--index-url', torch_index, *torch_packages], check=True)
    else:
        subprocess.run([*installer, "--index-url", torch_index, *torch_packages], check=True)
    apple_packages = ["mlx==0.32.3", "mlx-lm==0.32.0"] if translation_device == "mlx" else []
    transformers = "transformers==5.7.0" if sys.platform == "darwin" else "transformers==5.6.0"
    extensions = [*torch_packages, transformers, "accelerate", "funasr>=1.2,<2", "sentencepiece",
                  "silero-vad", "onnxruntime", "soundcard", "numpy", "soundfile", "librosa",
                  "huggingface-hub", "safetensors", *apple_packages]
    if uv:
        subprocess.run([sys.executable, '-u', '-m', 'ModuleFolders.Media.package_download', '--python', python,
                        '--index-url', indexes['pypi'], '--extra-index-url', torch_index, *extensions], check=True)
    else:
        subprocess.run([*installer, '--index-url', indexes['pypi'], '--extra-index-url', torch_index, *extensions], check=True)
    print(json.dumps({"runtime_python": python}), flush=True)


def download(root: Path, family: str, *, recognizer='sensevoice', scope='all') -> None:
    from ModuleFolders.Media.modelscope_download import download_model

    model = get_model(family)
    from ModuleFolders.Media.asr_catalog import get_recognizer
    asr = get_recognizer(recognizer)
    if scope not in {'all', 'asr', 'llm'}:
        raise ValueError('Unknown model download scope')
    if scope != 'llm':
        if asr.backend == 'gguf':
            for filename in (asr.filename, asr.projector):
                download_model(asr.repo, asr.revision, root / asr.directory, filename=filename)
        else:
            download_model(asr.repo, asr.revision, root / asr.directory)
    repo, revision = MODELS[model.key]
    if scope != 'asr':
        download_model(repo, revision, root / model.directory, filename=model.filename if model.backend == 'gguf' else '')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("probe", "devices", "install", "configure", "download"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--family", choices=tuple(model.key for model in TRANSLATION_MODELS), default="index")
    parser.add_argument("--managed", action="store_true")
    from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS
    parser.add_argument('--recognizer', choices=tuple(model.key for model in RECOGNITION_MODELS), default='sensevoice')
    parser.add_argument('--asr-device', choices=('auto', 'cpu', 'cuda:0', 'mps', 'vulkan', 'metal'), default='auto')
    parser.add_argument('--asr-endpoint', default='http://127.0.0.1:8001/v1')
    parser.add_argument('--download-scope', choices=('all', 'asr', 'llm'), default='all')
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
        import_errors = {}
        for name in ('torch', 'torchaudio'):
            try:
                versions[name + '_installed'] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
        if "torch" not in missing:
            try:
                import torch
                versions["torch"] = torch.__version__
                cuda = torch.cuda.is_available()
                mps = torch.backends.mps.is_available()
                if cuda:
                    gpu = torch.cuda.get_device_name(0)
            except Exception as error:
                from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
                import_errors['torch'] = safe_installer_line(f'{type(error).__name__}: {error}')
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
                except Exception as error:
                    from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
                    import_errors[name] = safe_installer_line(f'{type(error).__name__}: {error}')
                    missing.append(name)
        torch_version = versions.get('torch_installed', '').split('+')[0]
        audio_version = versions.get('torchaudio_installed', '').split('+')[0]
        if torch_version and audio_version and torch_version != audio_version:
            missing.append('matching torch/torchaudio versions')
        from ModuleFolders.Media.compute import detect_adapters, select_compute, selected_cuda_adapters
        adapters = detect_adapters()
        if cuda:
            adapters = selected_cuda_adapters(torch, adapters)
        checkpoint = get_model(args.family)
        compute_error = ""
        compute = {}
        try:
            compute = select_compute(args.device, gguf=checkpoint.backend == "gguf", cuda_available=cuda, adapters=adapters,
                                     mlx_compatible=checkpoint.family == "index", mps_available=mps)
            if compute["translation_device"] == "cuda:0":
                compute["cuda_check"] = cuda_execution_check(torch)
            if 'torch' not in missing:
                from ModuleFolders.Media.qwen_asr import recognition_device
                if args.recognizer == 'sensevoice' and args.asr_device != 'auto':
                    compute['asr_device'] = recognition_device(args.asr_device, args.recognizer, torch)
                if args.recognizer == 'sensevoice' and compute['asr_device'] == 'cuda:0' and compute['translation_device'] != 'cuda:0':
                    compute['cuda_check'] = cuda_execution_check(torch)
                if args.recognizer == 'sensevoice' and compute['asr_device'] == 'mps' and not mps:
                    raise RuntimeError('ASR MPS device is unavailable')
            from ModuleFolders.Media.asr_catalog import get_recognizer
            if get_recognizer(args.recognizer).backend == 'gguf':
                from ModuleFolders.Media.gguf_asr import select_asr_compute
                asr_compute = select_asr_compute(args.asr_device, cuda_available=cuda, adapters=adapters)
                compute['asr_device'] = asr_compute['translation_device']
                compute['asr_llama_backend'] = asr_compute['llama_backend']
                from ModuleFolders.Media.gguf_runtime import find_server
                if find_server(asr_compute['llama_backend']) is None:
                    missing.append('llama.cpp ASR ' + asr_compute['llama_backend'])
                if asr_compute['translation_device'] == 'cuda:0' and compute['translation_device'] != 'cuda:0':
                    compute['cuda_check'] = cuda_execution_check(torch)
            if get_recognizer(args.recognizer).backend == 'vllm':
                from ModuleFolders.Media.vllm_asr import available_models
                try:
                    if get_recognizer(args.recognizer).repo not in available_models(args.asr_endpoint):
                        raise RuntimeError('Local vLLM service is running a different model')
                except OSError:
                    raise RuntimeError('Local vLLM service unavailable; start it in Linux/WSL and retry') from None
                compute['asr_device'] = 'vllm-service'
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
                          "cuda": cuda, "gpu": gpu, "versions": versions, "import_errors": import_errors, "adapters": adapters,
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
        try:
            info = torch_runtime_info(runtime_python() if runtime_python().is_file() else sys.executable)
            if info.get('available'):
                adapters = [{'vendor': 'nvidia', 'name': info['name'], 'compute_capability': info['capability']}]
        except (OSError, RuntimeError, ValueError, IndexError, subprocess.TimeoutExpired):
            pass
        cuda_possible = any(adapter["vendor"] == "nvidia" for adapter in adapters)
        if args.device == "cuda:0":
            cuda_possible = True
        compute = select_compute(args.device, gguf=get_model(args.family).backend == "gguf",
                                 cuda_available=cuda_possible, adapters=adapters,
                                 mlx_compatible=get_model(args.family).family == "index")
        install_device = compute['asr_device']
        from ModuleFolders.Media.asr_catalog import get_recognizer
        if get_recognizer(args.recognizer).backend == 'gguf':
            from ModuleFolders.Media.gguf_asr import select_asr_compute
            asr_compute = select_asr_compute(args.asr_device, cuda_available=cuda_possible, adapters=adapters)
            if asr_compute['translation_device'] == 'cuda:0':
                install_device = 'cuda:0'
        check_device = 'cuda:0' if install_device == 'cuda:0' else compute['translation_device']
        if args.action == "install" or needs_install(check_device, recognizer=args.recognizer):
            install(install_device, translation_device=compute["translation_device"], recognizer=args.recognizer)
        else:
            print(json.dumps({"runtime_python": sys.executable}), flush=True)
        if args.action == "configure" and get_model(args.family).backend == "gguf":
            from ModuleFolders.Media.gguf_runtime import prepare
            prepare(backend=compute["llama_backend"])
        if args.action == 'configure':
            from ModuleFolders.Media.asr_catalog import get_recognizer
            if get_recognizer(args.recognizer).backend == 'gguf':
                from ModuleFolders.Media.gguf_asr import select_asr_compute
                from ModuleFolders.Media.gguf_runtime import prepare
                asr_compute = select_asr_compute(args.asr_device, cuda_available=cuda_possible, adapters=adapters)
                prepare(backend=asr_compute['llama_backend'])
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
        download(args.model_root, args.family, recognizer=args.recognizer, scope=args.download_scope)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if isinstance(exc, RuntimeError) and any(fragment in str(exc) for fragment in (
                "NVIDIA architecture", "Mixed legacy", "GPU architecture", "CUDA build", "Blackwell GPU", "Maxwell/Pascal")):
            print(json.dumps({"error_detail": str(exc)[:1600]}), flush=True)
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
