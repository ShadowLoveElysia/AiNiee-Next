#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi

    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi

    command -v uv >/dev/null 2>&1
}

if [ ! -f "Tools/WebServer/dist/index.html" ]; then
    echo "[ERROR] Tools/WebServer/dist/index.html not found."
    echo "Build WebServer assets first:"
    echo "  cd Tools/WebServer"
    echo "  npm install"
    echo "  npm run build"
    exit 1
fi

if [ "$(uname -s)" = "Linux" ]; then
    if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
        echo "[INFO] Headless Linux detected (DISPLAY/WAYLAND_DISPLAY not set)."
        echo "[INFO] GUI mode is disabled in headless environments."
        exit 2
    fi
fi

if ! ensure_uv && ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "[ERROR] Neither uv nor python is available."
    echo "The prebuilt GUI needs one of them to start the local backend."
    exit 1
fi

GUI_BIN="Tools/TauriShell/src-tauri/target/release/ainiee-tauri-shell"
MAC_APP="Tools/TauriShell/src-tauri/target/release/bundle/macos/AiNiee GUI PoC.app"

if [ -x "$GUI_BIN" ]; then
    echo "Starting AiNiee GUI (prebuilt binary)..."
    exec "$GUI_BIN"
fi

if [ "$(uname -s)" = "Darwin" ] && [ -d "$MAC_APP" ]; then
    echo "Starting AiNiee GUI (prebuilt app bundle)..."
    exec open "$MAC_APP"
fi

if [ "${AINIEE_GUI_DEV:-0}" != "1" ]; then
    echo "[ERROR] Prebuilt GUI binary not found:"
    echo "  $GUI_BIN"
    echo
    echo "No Node.js is required for end users, but you must provide a prebuilt binary."
    echo "If you are developing locally, run with:"
    echo "  AINIEE_GUI_DEV=1 ./LaunchGUI.sh"
    exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "[ERROR] cargo is not installed."
    echo "Please install Rust toolchain first: https://rustup.rs/"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "[ERROR] npm is not installed."
    echo "Please install Node.js first: https://nodejs.org/"
    exit 1
fi

cd Tools/TauriShell
echo "[DEV] Installing Tauri shell dependencies..."
npm install
echo "[DEV] Starting Tauri dev mode..."
npm run tauri:dev
