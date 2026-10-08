@echo off
setlocal
cd /d "%~dp0"

echo Setting up Ledgerly from source...
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.11 or newer is required for source setup.
        echo Download the Windows release ZIP to run without Python.
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import sys; sys.exit(sys.version_info < (3, 11))"
if %errorlevel% neq 0 (
    echo Python 3.11 or newer is required for source setup.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 exit /b 1
)

echo Installing runtime packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 exit /b 1

echo.
echo Setup complete. Run: .venv\Scripts\python.exe main.py
