$ErrorActionPreference = 'Stop'

if (-not (Test-Path .venv)) {
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
pyinstaller --onefile --windowed --name Foolproof --icon assets\foolproof-logo.ico --add-data "assets\foolproof-logo.png;assets" app.py

Write-Host "Built dist\Foolproof.exe"
