@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.11 or newer from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PYTHON_COMMAND=python"
) else (
  set "PYTHON_COMMAND=py -3"
)
%PYTHON_COMMAND% -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  %PYTHON_COMMAND% -m venv .venv
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency setup failed. Check your connection and the error above.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py %*
if errorlevel 1 pause
