#!/usr/bin/env bash
set -euo pipefail

# Codex runs inside Linux / WSL. Force an isolated uv environment so the
# project-local .venv does not get touched, otherwise mixed Windows/WSL venvs
# can break startup or dependency sync.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PATH="$SCRIPT_DIR/server.py"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

PYTHON_BIN="${AINIEE_MCP_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python)"
    else
        echo "AiNiee MCP launcher requires python3 or python on PATH." >&2
        exit 1
    fi
fi

exec uv run \
    --python "$PYTHON_BIN" \
    --isolated \
    --no-project \
    --quiet \
    --with mcp \
    --with fastapi \
    --with "uvicorn[standard]" \
    --with requests \
    python "$SERVER_PATH" \
    --transport stdio
