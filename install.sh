#!/usr/bin/env bash
#
# Install File Suite for the current user only.
# Requires a compiled executable at dist/FileSuite (see build.sh).
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BIN_SRC="dist/FileSuite"
ICON_SRC="organizer.jpg"

INSTALL_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons"

# ---------------------------------------------------------------------------
# 1. Sanity checks
# ---------------------------------------------------------------------------

if [ ! -f "$BIN_SRC" ]; then
    cat >&2 <<EOF
Error: compiled executable not found at '$BIN_SRC'.

File Suite must be built before it can be installed. From the project root run:

    ./build.sh

That produces dist/FileSuite. Then re-run:

    ./install.sh
EOF
    exit 1
fi

if [ ! -f "$ICON_SRC" ]; then
    echo "Warning: icon '$ICON_SRC' not found; the desktop entry will lack an icon." >&2
fi

# ---------------------------------------------------------------------------
# 2. Directories
# ---------------------------------------------------------------------------

mkdir -p "$INSTALL_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$ICON_DIR"

# ---------------------------------------------------------------------------
# 3. Copy binary
# ---------------------------------------------------------------------------

echo "Installing File Suite..."
install -m 0755 "$BIN_SRC" "$INSTALL_DIR/FileSuite"

ICON_LINE=""
if [ -f "$ICON_SRC" ]; then
    install -m 0644 "$ICON_SRC" "$ICON_DIR/filesuite-organizer.jpg"
    ICON_LINE="Icon=$ICON_DIR/filesuite-organizer.jpg"
fi

# ---------------------------------------------------------------------------
# 4. Desktop entry
# ---------------------------------------------------------------------------

DESKTOP_FILE="$APP_DIR/FileSuite.desktop"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=File Suite
Comment=Organize files and find duplicates in a directory
Exec=$INSTALL_DIR/FileSuite
$ICON_LINE
Terminal=false
Categories=Utility;System;
StartupNotify=true
EOF

chmod 0644 "$DESKTOP_FILE"

# ---------------------------------------------------------------------------
# 5. Refresh desktop database (optional)
# ---------------------------------------------------------------------------

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "File Suite installed successfully."
echo "  Executable: $INSTALL_DIR/FileSuite"
echo "  Desktop entry: $DESKTOP_FILE"