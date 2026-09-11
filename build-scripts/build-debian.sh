#!/usr/bin/env bash
# Build a tdsearch .deb package locally on Debian/Ubuntu (mirrors .github/workflows/build-installers.yml).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> [1/7] Checking system dependencies..."
REQUIRED_APT_PACKAGES=(python3 python3-venv python3-pip dpkg-dev libgl1 libegl1)
MISSING_APT_PACKAGES=()
for pkg in "${REQUIRED_APT_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        MISSING_APT_PACKAGES+=("$pkg")
    fi
done

if [ "${#MISSING_APT_PACKAGES[@]}" -gt 0 ]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "Missing packages: ${MISSING_APT_PACKAGES[*]}"
        echo "apt-get not found; install these packages manually for your distro and re-run."
        exit 1
    fi
    echo "==> Installing missing packages: ${MISSING_APT_PACKAGES[*]}"
    sudo apt-get update
    sudo apt-get install -y "${MISSING_APT_PACKAGES[@]}"
else
    echo "==> All required system packages are already installed."
fi

VENV_DIR=".build-venv"

echo "==> [2/7] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
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

echo "==> [5/7] Assembling .deb package tree for version ${VERSION}..."
rm -rf package-deb
mkdir -p package-deb/DEBIAN package-deb/usr/lib/tdsearch package-deb/usr/bin package-deb/usr/share/applications package-deb/usr/share/icons/hicolor/256x256/apps package-deb/usr/share/doc/tdsearch
cp -R dist/tdsearch package-deb/usr/lib/tdsearch/
ln -s /usr/lib/tdsearch/tdsearch/tdsearch package-deb/usr/bin/tdsearch
cp tdsearch/resources/icon.png package-deb/usr/share/icons/hicolor/256x256/apps/tdsearch.png
cp LICENSE package-deb/usr/share/doc/tdsearch/copyright
printf 'Package: tdsearch\nVersion: %s\nArchitecture: amd64\nMaintainer: Ivan Cvitic <cviticivan@gmail.com>\nDepends: libgl1, libegl1\nDescription: Desktop GUI for tabular data search\n' "$VERSION" > package-deb/DEBIAN/control
printf '[Desktop Entry]\nType=Application\nName=TDsearch\nExec=tdsearch\nIcon=tdsearch\nCategories=Utility;Office;\nTerminal=false\n' > package-deb/usr/share/applications/tdsearch.desktop

echo "==> [6/7] Building .deb package..."
dpkg-deb --build package-deb "dist/tdsearch-${VERSION}-amd64.deb"

deactivate

echo "==> [7/7] Done."
echo "  Package: dist/tdsearch-${VERSION}-amd64.deb"
echo "  Install with: sudo apt install ./dist/tdsearch-${VERSION}-amd64.deb"
