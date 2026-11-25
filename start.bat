@echo off
REM ================================================
REM  DocuQuery - one command start
REM  Creates the environment (first run), installs
REM  dependencies and starts the server.
REM ================================================
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Install Python 3 from https://python.org and try again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] First run - creating virtual environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
) else (
    echo [1/3] Virtual environment found.
)

".venv\Scripts\python.exe" -c "import flask, dotenv, pypdf" >nul 2>nul
if errorlevel 1 (
    echo [2/3] Installing dependencies - internet needed on first run...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check
    if errorlevel 1 (
        pause
        exit /b 1
    )
) else (
    echo [2/3] Dependencies already installed.
)

echo [3/3] Starting DocuQuery...
echo   First run downloads the local AI model (about 1 GB, one time only).
echo.
echo   Open  http://127.0.0.1:5000  in your browser
echo   Stop : press Ctrl+C
echo.
".venv\Scripts\python.exe" local_ai.py

pause
