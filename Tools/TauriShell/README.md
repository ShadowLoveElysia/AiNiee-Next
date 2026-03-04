# AiNiee Tauri Shell (PoC)

This is a minimal desktop shell PoC for AiNiee.

## What it does

- Starts a local Python host process: `tauri_web_host.py`
- The host starts `Tools.WebServer.web_server` on `127.0.0.1:18000` (default)
- Opens a Tauri native window that points to the local web UI
- Kills the Python host process when the app exits

## Current scope

- Works as a shell for existing Web UI and API
- Queue "run" endpoint remains host-integration dependent in current backend design
- Packaging/distribution is not finalized in this PoC

## Requirements

- `uv` available in PATH (preferred), or `python` fallback
- Rust toolchain installed (`cargo`, `rustc`)
- Node.js available
- Built Web UI assets under `Tools/WebServer/dist/index.html`

## Run (Windows PowerShell)

```powershell
cd Tools/TauriShell
npm.cmd install
npm.cmd run tauri:dev
```

## Build EXE (official Tauri command)

```powershell
cd Tools/TauriShell
npm.cmd run tauri:build:exe
```

Output:

- `Tools/TauriShell/src-tauri/target/release/ainiee-tauri-shell.exe`

## Quick launch scripts (project root)

- Windows: run `LaunchGUI.bat`
- macOS/Linux: run `./LaunchGUI.sh`
- Default mode: runs prebuilt GUI binary directly (no Node.js required)
- Dev mode fallback: set `AINIEE_GUI_DEV=1` to use `tauri dev`
- Linux headless mode: the script exits with a clear message and disables GUI startup

## Optional

- Override port:

```powershell
$env:AINIEE_GUI_PORT = "18001"
npm.cmd run tauri:dev
```
