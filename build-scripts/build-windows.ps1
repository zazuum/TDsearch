# Build TDsearch.exe locally on Windows (mirrors .github/workflows/build-installers.yml).
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> [1/6] Checking dependencies..."
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python is required. Install it first, e.g.: winget install Python.Python.3.12"
    exit 1
}
Write-Host "==> All required dependencies are present."

$VenvDir = ".build-venv"

Write-Host "==> [2/6] Creating Python virtual environment..."
python -m venv $VenvDir
& "$VenvDir\Scripts\Activate.ps1"

Write-Host "==> [3/6] Installing TDsearch and PyInstaller..."
python -m pip install --upgrade pip
python -m pip install . pyinstaller

Write-Host "==> [4/6] Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed --name TDsearch `
    --icon tdsearch/resources/icon.ico `
    --add-data "tdsearch/resources;resources" `
    --hidden-import PySide6.QtSvg `
    --collect-all xlsxgrep `
    --collect-all pyexcel `
    --collect-all pyexcel_io `
    --collect-all pyexcel_xls `
    --collect-all pyexcel_xlsx `
    --collect-all pyexcel_odsr `
    --collect-all lml `
    tdsearch/app.py

$Version = python -c "from tdsearch import __version__; print(__version__)"

Write-Host "==> [5/6] Packaging portable build for version $Version..."
Compress-Archive -Path "dist/TDsearch/*" -DestinationPath "dist/TDsearch-$Version-windows.zip" -Force

deactivate

Write-Host "==> [6/6] Building installer with Inno Setup..."
$Iscc = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "${env:ProgramFiles}\Inno Setup 6\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Iscc) {
    & $Iscc.FullName "/DMyAppVersion=$Version" "installer\windows\TDsearch.iss"
} else {
    Write-Host "Inno Setup not found; skipping installer build."
    Write-Host "Install it with: choco install innosetup   (or download from https://jrsoftware.org/isinfo.php)"
}

Write-Host "==> Done."
Write-Host "  Folder:    dist/TDsearch/"
Write-Host "  Zip:       dist/TDsearch-$Version-windows.zip"
Write-Host "  Installer: dist/TDsearch-$Version-windows-setup.exe (if Inno Setup was found)"
