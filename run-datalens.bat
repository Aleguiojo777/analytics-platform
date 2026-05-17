@echo off
setlocal

cd /d "%~dp0"
set PORT=3000
set CORS_ORIGINS=http://localhost:%PORT%,http://127.0.0.1:%PORT%

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.9+ is required. Install Python, then run this file again.
    pause
    exit /b 1
  )
)

echo Installing/updating DataLens dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo Starting DataLens at http://localhost:%PORT%
start "" "http://localhost:%PORT%"
".venv\Scripts\python.exe" server.py

pause
