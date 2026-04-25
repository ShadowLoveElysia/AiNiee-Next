#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BACKEND="${1:-}"
if [ -z "$BACKEND" ]; then
    case "$(uname -s)" in
        Darwin)
            BACKEND="metal"
            ;;
        *)
            BACKEND="cpu"
            ;;
    esac
fi

case "$BACKEND" in
    cpu)
        REQUIREMENTS_FILE="ModuleFolders/MangaCore/runtime/requirements_cpu.txt"
        ;;
    gpu)
        REQUIREMENTS_FILE="ModuleFolders/MangaCore/runtime/requirements_gpu.txt"
        ;;
    metal)
        REQUIREMENTS_FILE="ModuleFolders/MangaCore/runtime/requirements_metal.txt"
        ;;
    *)
        echo "[ERROR] Unsupported backend: $BACKEND"
        echo "Usage: ./prepare_comic.sh [cpu|gpu|metal]"
        exit 1
        ;;
esac

MANGA_VENV_DIR="$PROJECT_ROOT/.venv-manga"
MANGA_PYTHON="$MANGA_VENV_DIR/bin/python"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "[ERROR] Missing requirements file: $REQUIREMENTS_FILE"
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/ModuleFolders/MangaCore/runtime" ]; then
    echo "[ERROR] ModuleFolders/MangaCore/runtime is missing from the project root."
    exit 1
fi

echo "[1/4] Checking for uv..."
if ! command -v uv &> /dev/null; then
    echo "uv not found. Starting automatic installation..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi

    if ! command -v uv &> /dev/null; then
        echo "[ERROR] uv installation failed. Please install it manually from https://astral.sh/uv"
        exit 1
    fi
    echo "uv installed successfully."
else
    echo "uv is already installed."
fi

echo "[2/4] Creating manga runtime environment..."
uv venv "$MANGA_VENV_DIR" --python 3.12 --allow-existing

echo "[3/4] Installing manga runtime dependencies ($BACKEND)..."
uv pip install --python "$MANGA_PYTHON" -r "$REQUIREMENTS_FILE"

echo "[4/4] Downloading default MangaCore model assets..."
"$MANGA_PYTHON" "$PROJECT_ROOT/ModuleFolders/MangaCore/runtime/prepare_models.py"

echo "[Done] Manga runtime environment is ready at $MANGA_VENV_DIR"
echo "Main CLI dependencies are still managed by ./prepare.sh"
chmod +x Launch.sh prepare_comic.sh
