#!/usr/bin/env bash
# Build a tdsearch pacman package locally on Arch Linux (uses PyInstaller + makepkg).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "==> [1/7] Checking system dependencies..."
REQUIRED_PACMAN_PACKAGES=(python python-pip base-devel)
MISSING_PACMAN_PACKAGES=()
for pkg in "${REQUIRED_PACMAN_PACKAGES[@]}"; do
    if ! pacman -Qi "$pkg" >/dev/null 2>&1; then
        MISSING_PACMAN_PACKAGES+=("$pkg")
    fi
done

if [ "${#MISSING_PACMAN_PACKAGES[@]}" -gt 0 ]; then
    if ! command -v pacman >/dev/null 2>&1; then
        echo "Missing packages: ${MISSING_PACMAN_PACKAGES[*]}"
        echo "pacman not found; install these packages manually for your distro and re-run."
        exit 1
    fi
    echo "==> Installing missing packages: ${MISSING_PACMAN_PACKAGES[*]}"
    sudo pacman -Sy --needed --noconfirm "${MISSING_PACMAN_PACKAGES[@]}"
else
    echo "==> All required system packages are already installed."
fi

VENV_DIR=".build-venv"

echo "==> [2/7] Creating Python virtual environment..."
python -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "==> [3/7] Installing TDsearch and PyInstaller..."
python -m pip install --upgrade pip
python -m pip install . pyinstaller

echo "==> [4/7] Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed --name tdsearch \
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
deactivate

echo "==> [5/7] Assembling package tree for version ${VERSION}..."
PKG_ROOT="$PROJECT_DIR/package-arch"
rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT/usr/lib/tdsearch" "$PKG_ROOT/usr/bin" "$PKG_ROOT/usr/share/applications" "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps"

cp -R dist/tdsearch "$PKG_ROOT/usr/lib/tdsearch/"
ln -s /usr/lib/tdsearch/tdsearch/tdsearch "$PKG_ROOT/usr/bin/tdsearch"
cp tdsearch/resources/icon.png "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps/tdsearch.png"

cat > "$PKG_ROOT/usr/share/applications/tdsearch.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TDsearch
Exec=tdsearch
Icon=tdsearch
Categories=Utility;Office;
Terminal=false
EOF

echo "==> [6/7] Writing PKGBUILD and running makepkg..."
BUILD_DIR="$PROJECT_DIR/arch-build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cat > "$BUILD_DIR/PKGBUILD" <<EOF
# Maintainer: Ivan Cvitic <cviticivan@gmail.com>
pkgname=tdsearch
pkgver=${VERSION}
pkgrel=1
pkgdesc="Desktop GUI for tabular data search"
arch=('x86_64')
url="https://github.com/zazuum/TDsearch"
license=('MIT')
depends=('libgl' 'libegl' 'glibc')
options=('!strip' '!debug')

package() {
    cp -a "${PKG_ROOT}/usr" "\${pkgdir}/"
}
EOF

(cd "$BUILD_DIR" && makepkg -f --noconfirm)

mkdir -p dist
cp "$BUILD_DIR"/tdsearch-*.pkg.tar.* dist/

echo "==> [7/7] Done."
echo "  Package: dist/tdsearch-${VERSION}-1-x86_64.pkg.tar.zst"
echo "  Install with: sudo pacman -U ./dist/tdsearch-${VERSION}-1-x86_64.pkg.tar.zst"
