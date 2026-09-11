#!/usr/bin/env bash
# Build TDsearch.app, .dmg and .pkg locally on macOS (mirrors .github/workflows/build-installers.yml).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> [1/6] Checking dependencies..."
MISSING=()
command -v python3 >/dev/null 2>&1 || MISSING+=("python3")
xcode-select -p >/dev/null 2>&1 || MISSING+=("Xcode Command Line Tools")
command -v hdiutil >/dev/null 2>&1 || MISSING+=("hdiutil")
command -v productbuild >/dev/null 2>&1 || MISSING+=("productbuild")

if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "The following dependencies are missing: ${MISSING[*]}"
    if [[ " ${MISSING[*]} " == *"Xcode Command Line Tools"* ]]; then
        echo "Installing Xcode Command Line Tools (provides hdiutil/productbuild)..."
        xcode-select --install
        echo "Re-run this script after the Command Line Tools installation finishes."
    fi
    if [[ " ${MISSING[*]} " == *"python3"* ]]; then
        echo "Install Python 3 first, e.g.: brew install python@3.12"
    fi
    exit 1
fi
echo "==> All required dependencies are present."

VENV_DIR=".build-venv"

echo "==> [2/6] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "==> [3/6] Installing TDsearch and PyInstaller..."
python -m pip install --upgrade pip
python -m pip install . pyinstaller

echo "==> [4/6] Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed --name TDsearch \
    --icon tdsearch/resources/icon.icns \
    --add-data "tdsearch/resources:resources" \
    --hidden-import PySide6.QtSvg \
    --collect-all xlsxgrep \
    --collect-all pyexcel \
    --collect-all pyexcel_io \
    --collect-all pyexcel_xls \
    --collect-all pyexcel_xlsx \
    --collect-all pyexcel_odsr \
    --collect-all lml \
    tdsearch/app.py

VERSION=$(python -c "from tdsearch import __version__; print(__version__)")

echo "==> [5/6] Building .dmg and .pkg installers for version ${VERSION}..."
DMG_STAGING_DIR=$(mktemp -d)
cp -R dist/TDsearch.app "$DMG_STAGING_DIR/"
cp LICENSE "$DMG_STAGING_DIR/LICENSE.txt"
cp LICENSE "dist/TDsearch.app/Contents/Resources/LICENSE.txt"
ln -s /Applications "$DMG_STAGING_DIR/Applications"
hdiutil create -volname TDsearch -srcfolder "$DMG_STAGING_DIR" -ov -format UDZO "dist/TDsearch-${VERSION}-macos.dmg"
rm -rf "$DMG_STAGING_DIR"
productbuild --component dist/TDsearch.app /Applications "dist/TDsearch-${VERSION}-macos.pkg"

deactivate

echo "==> [6/6] Done."
echo "  App bundle: dist/TDsearch.app"
echo "  DMG:        dist/TDsearch-${VERSION}-macos.dmg"
echo "  PKG:        dist/TDsearch-${VERSION}-macos.pkg"
