#!/usr/bin/env bash

set -e

echo "Installing File Suite..."

# 1. Target directories creation
INSTALL_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"

mkdir -p "$INSTALL_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$ICON_DIR"

# 2. Copy binary and icon
if [ -f "dist/FileSuite" ]; then
    cp "dist/FileSuite" "$INSTALL_DIR/FileSuite"
else
    echo "⚠️ Compiled binary not found in dist/. Please ensure FileSuite is built."
    exit 1
fi

if [ -f "organizer.jpg" ]; then
    cp "organizer.jpg" "$ICON_DIR/filesuite-organizer.jpg"
fi

chmod +x "$INSTALL_DIR/FileSuite"

# 3. Create .desktop file
cat <<EOF > "$APP_DIR/FileSuite.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=File Suite
Comment=Modern Linux Desktop Organizer & Duplicate Cleaner
Exec=$INSTALL_DIR/FileSuite
Icon=$ICON_DIR/filesuite-organizer.jpg
Terminal=false
Categories=Utility;System;
StartupNotify=true
EOF

chmod +x "$APP_DIR/FileSuite.desktop"

# 4. Update desktop entry database if available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APP_DIR"
fi

echo "✅ File Suite installed successfully! You can now launch it from your application menu."