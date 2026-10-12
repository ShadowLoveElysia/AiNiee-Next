#!/bin/bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
source "$task_root/Tools/Bootstrap/unix_environment.sh"
detect_environment
if ! find_uv; then
    echo "[ERROR] uv was not found. Run bash prepare.sh or double-click Prepare.command first."
    exit 1
fi
echo "Starting AiNiee ($task_system / $task_arch)..."
exec "$task_uv" run ainiee_cli.py "$@"
