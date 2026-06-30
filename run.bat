@echo off
REM Launch Tab & Sheet Music Generator (works when PowerShell blocks .ps1 scripts).
cd /d "%~dp0"

set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" (
    echo Virtual env not found. Creating it...
    python -m venv .venv
    if errorlevel 1 exit /b 1
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)

echo Starting server at http://127.0.0.1:8000 ...
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
