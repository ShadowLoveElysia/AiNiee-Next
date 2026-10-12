#!/bin/bash
set -euo pipefail
export UV_NO_PROGRESS=false
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
source "$task_root/Tools/Bootstrap/unix_environment.sh"
trap 'task_status=$?; if [ "$task_status" -ne 0 ]; then echo "[ERROR] Media setup failed. Copy the complete error above for diagnosis." >&2; fi' EXIT
detect_environment
if [ "$task_system" != "Darwin" ] || [ "$task_arch" != "arm64" ]; then
    echo "[ERROR] This installer currently requires native Apple Silicon macOS. Windows: prepare_media.bat."
    exit 1
fi
task_device="${1:-auto}"
task_family="${2:-}"
task_recognizer="${4:-sensevoice}"
task_source="${3:-${AINIEE_MEDIA_PACKAGE_SOURCE:-}}"
if [ -z "$task_source" ]; then
    task_source=nju
    if [ -t 0 ]; then
        echo "Package source: 1. China / Nanjing University [default]  2. Official"
        read -r -p "Select 1 or 2, Enter for 1: " task_source_choice
        if [ "$task_source_choice" = "2" ]; then task_source=official; fi
    fi
fi
case "$task_source" in
    nju) task_pypi=https://mirror.nju.edu.cn/pypi/web/simple ;;
    official) task_pypi=https://pypi.org/simple ;;
    *) echo "[ERROR] Package source must be nju or official."; exit 1 ;;
esac
export AINIEE_MEDIA_PACKAGE_SOURCE="$task_source"
echo "Download source: $task_source"
case "$task_device" in
    auto|cpu|mlx|metal|mps) ;;
    *) echo "[ERROR] Device must be auto, cpu, mlx, metal or mps."; exit 1 ;;
esac
if ! find_uv; then
    echo "[ERROR] uv was not found. Run bash prepare.sh or Prepare.command first."
    exit 1
fi
"$task_uv" --version
echo "This installs inference extensions into Resource/MediaRuntime/macos-arm64."
echo "Downloads may require several GB. Model weights are downloaded separately."
echo "Full installer errors remain visible in this terminal."

echo "[1/5] Preparing isolated Python 3.12..."
select_python
if [ -z "$task_python" ]; then
    "$task_uv" python install 3.12
    task_python="$("$task_uv" python find 3.12)"
fi
"$task_python" -c 'import sys, platform; assert sys.version_info[:2] == (3,12); assert platform.machine() == "arm64", "Use native arm64 Python"'
task_runtime="$task_root/Resource/MediaRuntime/macos-arm64"
task_media_python="$task_runtime/bin/python"
if [ ! -f "$task_media_python" ]; then
    "$task_uv" venv --python "$task_python" --seed --index-url "$task_pypi" --allow-existing "$task_runtime"
fi
"$task_media_python" -c 'import sys, platform; print(sys.version); assert sys.version_info[:2] == (3,12); assert platform.machine() == "arm64"'
task_plan="$("$task_media_python" Tools/Bootstrap/prepare_media_runtime.py plan --device "$task_device" --family "$task_family" --recognizer "$task_recognizer" --format json)"
echo "$task_plan"
task_fields="$("$task_media_python" -c 'import json,sys; p=json.loads(sys.argv[1]); print(p["family"], p["translation_device"], p["backend"], p["llama_backend"] or "none", sep="\t")' "$task_plan")"
IFS=$'\t' read -r task_family task_selected task_backend task_llama <<< "$task_fields"
if [ "$task_selected" = "mlx" ]; then
    "$task_media_python" -c 'import platform; assert tuple(map(int,platform.mac_ver()[0].split(".")[:2])) >= (14,0), "MLX requires macOS 14+; select MPS or Metal GGUF explicitly"'
fi

echo "[2/5] Installing matching Torch and torchaudio..."
"$task_media_python" -u -m ModuleFolders.Media.package_download --python "$task_media_python" --index-url "$task_pypi" 'torch==2.9.1' 'torchaudio==2.9.1'
echo "[3/5] Installing recognition, translation and audio libraries..."
task_transformers='transformers==5.7.0'
task_packages=("$task_transformers" accelerate 'funasr>=1.2,<2' sentencepiece silero-vad
               onnxruntime soundcard numpy soundfile librosa huggingface-hub safetensors requests)
if [ "$task_selected" = "mlx" ]; then
    task_packages+=('mlx==0.32.3' 'mlx-lm==0.32.0')
fi
"$task_media_python" -u -m ModuleFolders.Media.package_download --python "$task_media_python" --index-url "$task_pypi" "${task_packages[@]}"

echo "[4/5] Preparing the selected translation backend..."
if [ "$task_backend" = "gguf" ]; then
    "$task_media_python" -u -m ModuleFolders.Media.gguf_runtime --backend "$task_llama"
fi
task_asr_llama="$("$task_media_python" -c 'import json,sys; print(json.loads(sys.argv[1]).get("asr_llama_backend", ""))' "$task_plan")"
if [ -n "$task_asr_llama" ] && [ "$task_asr_llama" != "$task_llama" ]; then
    "$task_media_python" -u -m ModuleFolders.Media.gguf_runtime --backend "$task_asr_llama"
fi
echo "[5/5] Verifying inference libraries and saving the runtime..."
"$task_media_python" Tools/Bootstrap/prepare_media_runtime.py verify --device "$task_device" --family "$task_family" --recognizer "$task_recognizer"
echo "Inference environment is ready. Reopen the controller and check the environment."

echo "Checking the optional native system-audio helper..."
if command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then
    if ! "$task_media_python" -u -m ModuleFolders.Media.macos_audio --check; then
        echo "[WARNING] Inference is ready, but native system audio preparation failed. See the error above."
        echo "Use Xcode 15.3+ Command Line Tools, or explicitly select a microphone/virtual audio input."
    fi
else
    echo "[INFO] Native system audio requires Xcode 15.3+ Command Line Tools. Run xcode-select --install, then rerun this script."
fi
echo "Model weights, recording permission and live audio still require checks in the controller."
