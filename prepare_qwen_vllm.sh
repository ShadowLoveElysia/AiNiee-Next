#!/bin/bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
source "$task_root/Tools/Bootstrap/unix_environment.sh"
detect_environment
if [ "$task_system" != Linux ]; then
    echo "Run this script in Linux/WSL with NVIDIA CUDA. vLLM does not run natively on macOS/Windows."
    exit 1
fi
if ! find_uv; then echo "Install uv first."; exit 1; fi
select_python
if [ -z "$task_python" ]; then
    "$task_uv" python install 3.12
    task_python="$("$task_uv" python find 3.12)"
fi
"$task_python" -u -m ModuleFolders.Media.vllm_service install --source "${1:-nju}"
"$task_python" -u -m ModuleFolders.Media.vllm_service download --recognizer "${2:-qwen-vllm-0.6b}" --model-root "${3:-tmp/models}"
echo "Setup complete. Start the service using LaunchQwenVllm.sh; select the matching vLLM recognizer in the controller."
