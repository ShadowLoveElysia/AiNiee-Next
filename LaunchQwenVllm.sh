#!/bin/bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
exec "$task_root/Resource/MediaRuntime/vllm-asr-linux/bin/python" -u -m ModuleFolders.Media.vllm_service serve "$@"
