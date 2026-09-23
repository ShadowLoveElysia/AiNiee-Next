#!/usr/bin/env bash
set -euo pipefail

# Reuse the project's existing Python environment first. The project lockfile
# requires Python 3.12.*; only use the isolated fallback when explicitly asked.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PATH="$SCRIPT_DIR/server.py"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [[ -n "${AINIEE_MCP_PYTHON:-}" ]]; then
    PYTHON_BIN="$AINIEE_MCP_PYTHON"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/.venv-win/Scripts/python.exe" && "${AINIEE_MCP_USE_WINDOWS_VENV:-}" == "1" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv-win/Scripts/python.exe"
else
    PYTHON_BIN="3.12"
fi

# AiNiee-Next requires Python 3.12.*. Do not silently let uv resolve the
# command's ambient Python (older interpreters fail while importing the model
# types, and the client then reports a misleading broken stdio pipe).
if [[ "$PYTHON_BIN" != "3.12" && "$PYTHON_BIN" != "python3.12" ]]; then
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "$PYTHON_BIN")"
    else
        echo "AINIEE_MCP_PYTHON must point to Python 3.12.* (got: $PYTHON_BIN)." >&2
        exit 1
    fi
fi

if [[ "$PYTHON_BIN" != "3.12" && "$PYTHON_BIN" != "python3.12" ]]; then
    PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
    if [[ "$PYTHON_VERSION" != "3.12" ]]; then
        echo "AiNiee MCP requires Python 3.12.*; detected ${PYTHON_VERSION:-unknown}." >&2
        exit 1
    fi
fi

if [[ "$PYTHON_BIN" == "$PROJECT_ROOT/.venv/bin/python" ]]; then
    exec uv run --directory "$PROJECT_ROOT" --python "$PYTHON_BIN" python "$SERVER_PATH" --transport stdio
fi

exec uv run --python "$PYTHON_BIN" --isolated --no-project --quiet \
    --with mcp --with fastapi --with "uvicorn[standard]" --with requests \
    python "$SERVER_PATH" --transport stdio
