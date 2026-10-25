#!/usr/bin/env bash
#
# Build File Suite into dist/FileSuite.app with PyInstaller and pack it into
# dist/FileSuite-macos-<arch>-v<version>.dmg plus a .sha256 file next to it.
# Runs on macOS only, for the architecture of the machine it runs on.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Error: this script builds the macOS app and must run on macOS." >&2
    exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Error: '$PYTHON_BIN' was not found in PATH." >&2
    exit 1
fi

VERSION="$("$PYTHON_BIN" -c "import version; print(version.__version__)")"
ARCH="$(uname -m)"
case "$ARCH" in
    arm64 | x86_64) ;;
    *)
        echo "Error: unsupported architecture '$ARCH'." >&2
        exit 1
        ;;
esac

APP="dist/FileSuite.app"
PLIST="$APP/Contents/Info.plist"
DMG_NAME="FileSuite-macos-${ARCH}-v${VERSION}.dmg"
DMG="dist/$DMG_NAME"

echo "=========================================="
echo " Building File Suite v${VERSION} (${ARCH})"
echo "=========================================="

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6,<7"

echo "Building FileSuite.app with PyInstaller..."
pyinstaller --noconfirm --clean packaging/macos/FileSuite.spec

fail() {
    echo "Error: $*" >&2
    exit 1
}

plist_value() {
    plutil -extract "$1" raw -o - "$PLIST"
}

check_plist() {
    local actual
    actual="$(plist_value "$1")"
    [ "$actual" = "$2" ] || fail "Info.plist $1 is '$actual', expected '$2'"
}

echo "Verifying $APP ..."
[ -x "$APP/Contents/MacOS/FileSuite" ] || fail "build did not produce $APP/Contents/MacOS/FileSuite"
plutil -p "$PLIST"
check_plist CFBundleIdentifier io.github.teppe21.filesuite
check_plist CFBundleShortVersionString "$VERSION"
check_plist CFBundleVersion "$VERSION"
check_plist CFBundleName "File Suite"
check_plist CFBundleIconFile organizer.icns
[ -f "$APP/Contents/Resources/organizer.icns" ] || fail "organizer.icns is missing from the bundle"

[ "$(lipo -archs "$APP/Contents/MacOS/FileSuite")" = "$ARCH" ] || fail "FileSuite is not a $ARCH-only executable"

# PyInstaller keeps data in Contents/Resources and links it from Contents/Frameworks
# (where sys._MEIPASS points), so -L makes find see both layouts.
for name in organizer.jpg organizer-small.png; do
    [ -n "$(find -L "$APP/Contents" -name "$name" -type f -print -quit)" ] || fail "$name is missing from the bundle"
done
[ -n "$(find -L "$APP/Contents" -type d -path "*customtkinter/assets" -print -quit)" ] \
    || fail "CustomTkinter assets are missing from the bundle"
# The Finder Trash backend imports these inside a function; a missing one only
# shows up when the user trashes a file.
for module in objc Foundation CoreFoundation; do
    [ -n "$(find -L "$APP/Contents" -path "*/$module/_*" -name "*.so" -print -quit)" ] \
        || fail "pyobjc module '$module' is missing from the bundle"
done

# PyInstaller signs ad hoc on Apple silicon (the kernel refuses unsigned arm64
# code). It can leave a signature that does not verify, for example when the
# bundle was assembled after the signing step or on an Intel build, so sign the
# whole bundle ad hoc again and require it to verify.
if ! codesign --verify --deep --strict --verbose=2 "$APP"; then
    echo "Signature does not verify, signing ad hoc ..."
    codesign --force --deep --sign - "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"
fi

echo "Creating $DMG ..."
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
ditto "$APP" "$STAGING/FileSuite.app"
ln -s /Applications "$STAGING/Applications"
rm -f "$DMG"
# hdiutil fails now and then on CI runners with "Resource busy".
for attempt in 1 2 3; do
    if hdiutil create -volname "File Suite" -srcfolder "$STAGING" -ov -format UDZO "$DMG"; then
        break
    fi
    [ "$attempt" -lt 3 ] || fail "hdiutil create failed 3 times"
    echo "hdiutil create failed (attempt $attempt of 3), retrying ..."
    rm -f "$DMG"
    sleep 5
done

# macOS has no sha256sum; shasum writes the same "<hash>  <file>" lines.
(cd dist && shasum -a 256 "$DMG_NAME" > "$DMG_NAME.sha256")

echo "=========================================="
echo " Build complete: $APP"
echo " DMG:    $DMG"
echo " SHA-256: $(cat "$DMG.sha256")"
echo "=========================================="
