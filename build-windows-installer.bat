@echo off
setlocal
cd /d "%~dp0"

set "LEDGERLY_VERSION=%~1"
if not defined LEDGERLY_VERSION set "LEDGERLY_VERSION=0.1.0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.11 or newer is required to build Ledgerly.
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo Python 3.11 or newer is required to build Ledgerly.
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    echo Creating build environment...
    %PYTHON% -m venv .venv-build
    if errorlevel 1 exit /b 1
)

echo Installing build dependencies...
".venv-build\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo Building the desktop application...
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm Ledgerly.spec
if errorlevel 1 exit /b 1

set "ISCC="
where ISCC.exe >nul 2>nul
if %errorlevel% equ 0 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo Inno Setup 6 is required to create LedgerlySetup.exe.
    echo Download it from https://jrsoftware.org/isdl.php
    exit /b 1
)

echo Building Ledgerly %LEDGERLY_VERSION% installer...
"%ISCC%" "installer\Ledgerly.iss"
if errorlevel 1 exit /b 1

echo.
echo Installer created: dist\LedgerlySetup.exe
