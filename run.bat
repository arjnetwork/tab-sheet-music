@echo off
REM Launch Tab & Sheet Music Generator (works when PowerShell blocks .ps1 scripts).
cd /d "%~dp0"

set PY=%~dp0.venv\Scripts\python.exe

if not exist "%PY%" (
    echo Virtual env not found. Creating it...
    echo First run can take several minutes while packages download.
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create virtual env.
        echo Install Python 3.10+ from python.org and make sure "python" works in a terminal.
        goto :fail
    )
    "%PY%" -m pip install --upgrade pip
    if errorlevel 1 goto :fail
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: pip install failed.
        goto :fail
    )
)

echo.
echo Starting server at http://127.0.0.1:8000
echo Open that address in your browser.
echo To stop the server: click this window and press Ctrl+C
echo.

"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
    echo.
    echo Server exited with an error.
    echo Common cause: port 8000 is already in use ^(another copy may still be running^).
)

echo.
echo Server stopped.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
