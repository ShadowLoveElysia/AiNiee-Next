#!/usr/bin/env bash
set -euo pipefail

# AiNiee Skills Server launcher
# Starts the Skills HTTP server using uv when available, with a Python fallback
# for installed/source distributions that do not ship uv.
#
# Usage:
#   ./Tools/Skills/launcher.sh [--port PORT] [--host HOST]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVER_PATH="$SCRIPT_DIR/server.py"

cd "$PROJECT_DIR"

echo "[Skills] Starting AiNiee Skills Server from $PROJECT_DIR" >&2
if command -v uv >/dev/null 2>&1; then
    exec uv run python "$SERVER_PATH" "$@"
fi

PYTHON_BIN="${AINIEE_PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[Skills] Neither uv nor $PYTHON_BIN is available." >&2
    echo "[Skills] Install the project environment or set AINIEE_PYTHON." >&2
    exit 1
fi
exec "$PYTHON_BIN" "$SERVER_PATH" "$@"
