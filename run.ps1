# Launch Tab & Sheet Music Generator locally.
# Usage:  ./run.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$py = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Virtual env not found. Creating it..." -ForegroundColor Yellow
    python -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
}

Write-Host "Starting server at http://127.0.0.1:8000 ..." -ForegroundColor Green
& $py -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
