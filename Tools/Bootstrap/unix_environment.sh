#!/bin/bash
# Sourced by launchers to keep platform and interpreter selection consistent.

detect_environment() {
    task_system="$(uname -s)"
    task_arch="$(uname -m)"
    case "$task_system" in
        Darwin)
            if [ "$(sysctl -in hw.optional.arm64 2>/dev/null || true)" = "1" ] && [ "$task_arch" != "arm64" ]; then
                echo "[ERROR] Apple Silicon is running under Rosetta. Open a native Terminal and rerun."
                return 1
            fi
            ;;
        Linux) ;;
        *) echo "[ERROR] Unsupported system: $task_system. Windows users should run prepare.bat."; return 1 ;;
    esac
    export UV_PROJECT_ENVIRONMENT="$task_root/tmp/environments/$(printf '%s' "$task_system" | tr '[:upper:]' '[:lower:]')-$task_arch"
}

find_uv() {
    task_uv=""
    if command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
        task_uv="$(command -v uv)"
        return 0
    fi
    for task_candidate in "${UV_INSTALL_DIR:-$HOME/.local/bin}/uv" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$task_candidate" ] && "$task_candidate" --version >/dev/null 2>&1; then
            task_uv="$task_candidate"
            export PATH="$(dirname "$task_uv"):$PATH"
            return 0
        fi
    done
    return 1
}

install_uv() {
    local task_installer task_result=0
    task_installer="$(mktemp "${TMPDIR:-/tmp}/ainiee-uv-install.XXXXXX")"
    if command -v curl >/dev/null 2>&1; then
        curl -fLsS --connect-timeout 20 --max-time 180 https://astral.sh/uv/install.sh -o "$task_installer" || task_result=$?
    elif command -v wget >/dev/null 2>&1; then
        wget --timeout=30 -q https://astral.sh/uv/install.sh -O "$task_installer" || task_result=$?
    else
        echo "[ERROR] Install curl or wget, then rerun setup."
        task_result=1
    fi
    if [ "$task_result" -eq 0 ]; then
        sh "$task_installer" || task_result=$?
    fi
    rm -f "$task_installer"
    if [ "$task_result" -ne 0 ] || ! find_uv; then
        echo "[ERROR] uv installation failed. See https://docs.astral.sh/uv/getting-started/installation/"
        return 1
    fi
}

select_python() {
    task_python=""
    local task_candidate task_path
    # Prefer an existing Tk-enabled 3.12 interpreter before managed Python.
    for task_candidate in "$UV_PROJECT_ENVIRONMENT/bin/python" python3.12 python3 \
                          /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
                          /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12; do
        task_path="$(command -v "$task_candidate" 2>/dev/null || true)"
        if [ -n "$task_path" ] && "$task_path" -c 'import sys, tkinter; assert sys.version_info[:2] == (3, 12)' >/dev/null 2>&1; then
            if [ "$task_system" = "Darwin" ] && [ "$task_arch" = "arm64" ] && ! "$task_path" -c 'import platform; assert platform.machine() == "arm64"' >/dev/null 2>&1; then
                continue
            fi
            task_python="$task_path"
            return 0
        fi
    done
    if find_uv; then
        task_python="$("$task_uv" python find 3.12 2>/dev/null || true)"
    fi
}

tk_help() {
    if [ "$task_system" = "Darwin" ]; then
        echo "Install Python 3.12 with Tk from https://www.python.org/downloads/macos/ ."
        echo "Homebrew users need python@3.12 and python-tk@3.12. Rerun Prepare.command afterward."
    else
        echo "Install your distribution's Tk support for Python 3.12, then rerun bash prepare.sh."
        echo "A graphical session (DISPLAY or WAYLAND_DISPLAY) is also required for the controller."
    fi
}
