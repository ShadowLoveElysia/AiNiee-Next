#!/bin/bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
source "$task_root/Tools/Bootstrap/unix_environment.sh"

detect_environment
echo "[1/4] Detected $task_system / $task_arch"
echo "Environment: $UV_PROJECT_ENVIRONMENT"
if ! find_uv; then
    echo "uv not found. Installing uv for the current user..."
    install_uv
fi
"$task_uv" --version

echo "[2/4] Preparing Python 3.12..."
select_python
if [ -z "$task_python" ]; then
    "$task_uv" python install 3.12
    task_python="$("$task_uv" python find 3.12)"
fi
"$task_python" -c 'import platform, sys; assert sys.version_info[:2] == (3, 12); print("Python", platform.python_version(), platform.machine())'
if [ "$task_system" = "Darwin" ] && [ "$task_arch" = "arm64" ]; then
    "$task_python" -c 'import platform; assert platform.machine() == "arm64", "Use native arm64 Python instead of Rosetta"'
fi

echo "[3/4] Syncing project dependencies..."
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
"$task_uv" sync --python "$task_python"
echo "[4/4] Checking the configured environment..."
"$task_uv" run --no-sync python -c 'import sys, rich, rapidjson, requests; assert sys.version_info[:2] == (3, 12); print("Core runtime ready")'
if "$task_uv" run --no-sync python -c 'import tkinter' >/dev/null 2>&1; then
    echo "Tk is available for the live translation controller."
else
    echo "[INFO] Core runtime is ready, but live translation needs Python 3.12 with Tk."
    tk_help
fi
chmod +x Launch.sh Prepare.command Launch.command LaunchLive.command
echo "Environment is ready. Run bash Launch.sh to start AiNiee."
if [ "$task_system" = "Darwin" ]; then
    echo "You can also double-click Launch.command or LaunchLive.command in Finder."
fi
echo "Prepare inference libraries and models inside the live translation controller."
