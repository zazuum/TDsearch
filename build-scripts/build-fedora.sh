#!/usr/bin/env bash
# Build a tdsearch .rpm package locally on Fedora (mirrors .github/workflows/build-installers.yml).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> [1/7] Checking system dependencies..."
REQUIRED_DNF_PACKAGES=(python3 python3-pip rpm-build findutils)
MISSING_DNF_PACKAGES=()
for pkg in "${REQUIRED_DNF_PACKAGES[@]}"; do
    if ! rpm -q "$pkg" >/dev/null 2>&1; then
        MISSING_DNF_PACKAGES+=("$pkg")
    fi
done

if [ "${#MISSING_DNF_PACKAGES[@]}" -gt 0 ]; then
    if ! command -v dnf >/dev/null 2>&1; then
        echo "Missing packages: ${MISSING_DNF_PACKAGES[*]}"
        echo "dnf not found; install these packages manually for your distro and re-run."
        exit 1
    fi
    echo "==> Installing missing packages: ${MISSING_DNF_PACKAGES[*]}"
    sudo dnf install -y "${MISSING_DNF_PACKAGES[@]}"
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
    --exclude-module PySide6.scripts \
    --exclude-module PySide6.scripts.deploy_lib \
    --exclude-module PySide6.scripts.project_lib \
    --exclude-module PySide6.scripts.pyside_tool \
    --collect-all xlsxgrep \
    --collect-all pyexcel \
    --collect-all pyexcel_io \
    --collect-all pyexcel_xls \
    --collect-all pyexcel_xlsx \
    --collect-all pyexcel_odsr \
    --collect-all lml \
    tdsearch/app.py

VERSION=$(python -c "from tdsearch import __version__; print(__version__)")

echo "==> [5/7] Assembling .rpm package tree for version ${VERSION}..."
rm -rf rpmbuild package-rpm
mkdir -p rpmbuild/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p package-rpm/usr/lib/tdsearch package-rpm/usr/bin package-rpm/usr/share/applications package-rpm/usr/share/icons/hicolor/256x256/apps package-rpm/usr/share/doc/tdsearch

cp -R dist/tdsearch package-rpm/usr/lib/tdsearch/
ln -s /usr/lib/tdsearch/tdsearch/tdsearch package-rpm/usr/bin/tdsearch
cp tdsearch/resources/icon.png package-rpm/usr/share/icons/hicolor/256x256/apps/tdsearch.png
cp LICENSE package-rpm/usr/share/doc/tdsearch/LICENSE

cat > package-rpm/usr/share/applications/tdsearch.desktop <<EOF
[Desktop Entry]
Type=Application
Name=TDsearch
Exec=tdsearch
Icon=tdsearch
Categories=Utility;Office;
Terminal=false
EOF

tar -C package-rpm -czf "rpmbuild/SOURCES/tdsearch-${VERSION}.tar.gz" .

cat > rpmbuild/SPECS/tdsearch.spec <<EOF
Name: tdsearch
Version: ${VERSION}
Release: 1%{?dist}
Summary: Desktop GUI for tabular data search
License: MIT
BuildArch: x86_64
Source0: %{name}-%{version}.tar.gz

%global debug_package %{nil}
%undefine _missing_build_ids_terminate_build
%define __debug_install_post %{nil}

%description
Desktop GUI for tabular data search.

%prep
%setup -q -c -T
tar -xzf %{SOURCE0}

%install
mkdir -p %{buildroot}
cp -a . %{buildroot}/

%files
/usr
%license /usr/share/doc/tdsearch/LICENSE

%changelog
* $(date "+%a %b %d %Y") Ivan Cvitic <cviticivan@gmail.com> - ${VERSION}-1
- Local Fedora package build
EOF

echo "==> [6/7] Building .rpm package..."
rpmbuild \
    --define "_topdir $(pwd)/rpmbuild" \
    --define "debug_package %{nil}" \
    -bb rpmbuild/SPECS/tdsearch.spec

cp rpmbuild/RPMS/x86_64/*.rpm "dist/"

deactivate

echo "==> [7/7] Done."
echo "  Package: dist/tdsearch-${VERSION}-1.fc*.x86_64.rpm"
echo "  Install with: sudo dnf install ./dist/tdsearch-${VERSION}-1.fc*.x86_64.rpm"
