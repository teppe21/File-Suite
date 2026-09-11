#!/usr/bin/env bash
#
# Build File Suite into a standalone executable using PyInstaller.
# The result is written to dist/FileSuite and can then be installed with
# ./install.sh.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Error: '$PYTHON_BIN' was not found in PATH." >&2
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6,<7"

echo "Building FileSuite with PyInstaller..."
pyinstaller \
    --noconfirm \
    --clean \
    --name FileSuite \
    --onefile \
    --add-data "organizer.jpg:." \
    --collect-data customtkinter \
    --collect-submodules customtkinter \
    main.py

if [ ! -f "dist/FileSuite" ]; then
    echo "Error: build did not produce dist/FileSuite" >&2
    exit 1
fi

echo "Build complete: dist/FileSuite"
echo "You can now run ./install.sh"