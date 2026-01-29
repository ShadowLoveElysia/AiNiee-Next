#!/bin/bash

echo "[1/3] Checking for uv..."
if ! command -v uv &> /dev/null; then
    echo "uv not found. Starting automatic installation..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Try multiple possible paths for uv
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    elif [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    fi

    # Add to PATH if not already there
    if [ -d "$HOME/.local/bin" ] && [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv &> /dev/null; then
        echo "[ERROR] uv installation failed. Please install it manually from https://astral.sh/uv"
        echo "Try running: export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
    echo "uv installed successfully."
else
    echo "uv is already installed."
fi

echo "[2/3] Installing Python 3.12 and creating virtual environment..."
uv python install 3.12
rm -rf .venv
uv venv --python 3.12

echo "[3/3] Syncing project dependencies..."
uv sync

# Add python-multipart for web server functionality
echo "Adding additional dependencies..."
uv add python-multipart

if [ $? -ne 0 ]; then
    echo "[ERROR] Dependency sync failed."
    exit 1
fi

echo "[4/4] Done!"
echo "Environment is ready. You can now use ./Launch.sh to start AiNiee CLI."
chmod +x Launch.sh