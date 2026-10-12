#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
task_root="$PWD"
source "$task_root/Tools/Bootstrap/unix_environment.sh"
if [ "$(uname -s)" != "Darwin" ]; then
    echo "Use python -m ModuleFolders.Media on Windows/Linux."
    exit 1
fi
detect_environment
select_python
if [ -z "$task_python" ] || ! "$task_python" -c 'import tkinter' >/dev/null 2>&1; then
    tk_help
    if [ -t 0 ]; then
        read -r -p "Press Enter to close..." _
    fi
    exit 1
fi
task_arch="$("$task_python" -c 'import platform; print(platform.machine())')"
if [ "$(sysctl -in hw.optional.arm64 2>/dev/null || true)" = "1" ] && [ "$task_arch" != "arm64" ]; then
    echo "Apple Silicon detected, but Python is running under Rosetta. Install native arm64 Python for MLX."
    read -r -p "Press Enter to close..." _
    exit 1
fi
task_runtime="Resource/MediaDesktop/macos-$task_arch"
if [ ! -x "$task_runtime/bin/python" ]; then
    "$task_python" -m venv "$task_runtime"
fi
if ! "$task_runtime/bin/python" -c 'import rich, rapidjson, requests' 2>/dev/null; then
    echo "Preparing isolated desktop dependencies..."
    "$task_runtime/bin/python" -m pip install 'rich>=13.9.4' python-rapidjson requests
fi
"$task_runtime/bin/python" -m ModuleFolders.Media "$@"
