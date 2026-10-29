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
) else (
    echo [1/3] Virtual environment found.
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q --disable-pip-version-check

echo [3/3] Starting DocuQuery...
echo.
echo   Open  http://127.0.0.1:5000  in your browser
echo   Login: demo@example.com / demo123
echo   Stop : press Ctrl+C
echo.
".venv\Scripts\python.exe" run.py

pause
