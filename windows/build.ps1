# Build UseBar.exe (Windows system-tray app) with PyInstaller.
# Run from the repo root or this folder:  powershell -ExecutionPolicy Bypass -File windows\build.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$root = Split-Path -Parent $here

Write-Host "==> installing build deps"
python -m pip install --upgrade pip | Out-Null
python -m pip install -r "$here\requirements.txt" pyinstaller | Out-Null

Write-Host "==> bundling engines next to the entry script"
# PyInstaller picks up `engines` via the --paths root and hidden imports.
Push-Location $root
try {
    pyinstaller --noconfirm --clean --onefile --windowed `
        --name UseBar `
        --paths "$root" `
        --hidden-import engines `
        --hidden-import engines.claude `
        --hidden-import engines.cursor `
        --hidden-import engines.config `
        --hidden-import engines.common `
        --collect-submodules pystray `
        --collect-submodules PIL `
        "$here\usebar_win.py"
    Write-Host "==> built: $root\dist\UseBar.exe"
}
finally {
    Pop-Location
}
