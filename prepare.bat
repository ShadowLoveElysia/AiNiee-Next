@echo off
setlocal
title AiNiee CLI - Prepare Environment
pushd "%~dp0" >nul
if errorlevel 1 exit /b 1

REM Keep the Windows dependency environment separate from a WSL/Linux .venv.
REM This avoids uv touching Linux-only symlinks such as ".venv\lib64".
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win"

if exist ".venv\lib64" (
    echo [INFO] Detected a non-Windows .venv. Using "%UV_PROJECT_ENVIRONMENT%" for dependency setup.
)

echo [1/4] Detected Windows: %PROCESSOR_ARCHITECTURE%
echo Environment: "%UV_PROJECT_ENVIRONMENT%"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
if defined UV_INSTALL_DIR set "PATH=%UV_INSTALL_DIR%;%PATH%"
echo Checking for uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo uv not found. Starting automatic installation...
    powershell -NoProfile -ExecutionPolicy ByPass -c "$ErrorActionPreference = 'Stop'; irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 goto :failed
    
    REM Discover current and legacy uv install locations.
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
    
    uv --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] uv installation failed. Please install it manually from https://astral.sh/uv
        popd
        pause
        exit /b 1
    )
    echo uv installed successfully.
) else (
    echo uv is already installed.
)

echo [2/4] Preparing Python 3.12...
uv python install 3.12
if errorlevel 1 goto :failed

echo [3/4] Syncing project dependencies...
uv sync --python 3.12

if errorlevel 1 (
    echo [ERROR] Dependency sync failed.
    popd
    pause
    exit /b 1
)

echo [4/4] Checking the configured environment...
uv run --no-sync python -c "import sys, rich, rapidjson, requests; assert sys.version_info[:2] == (3, 12); print('Core runtime ready')"
if errorlevel 1 goto :failed
uv run --no-sync python -c "import tkinter" >nul 2>&1
if errorlevel 1 echo [INFO] Live translation needs Python 3.12 with Tk.
echo Done!
echo Environment is ready. You can now use Launch.bat to start AiNiee CLI.
popd
pause
exit /b 0

:failed
echo [ERROR] Environment setup failed. Check network access and the error above.
popd
pause
exit /b 1
