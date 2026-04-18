@echo off
setlocal
title AiNiee CLI - Prepare Environment
pushd "%~dp0" >nul

REM Keep the Windows dependency environment separate from a WSL/Linux .venv.
REM This avoids uv touching Linux-only symlinks such as ".venv\lib64".
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win"

if exist ".venv\lib64" (
    echo [INFO] Detected a non-Windows .venv. Using "%UV_PROJECT_ENVIRONMENT%" for dependency setup.
)

echo [1/3] Checking for uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo uv not found. Starting automatic installation...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    
    REM Add uv to current session PATH
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    
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

echo [2/3] Syncing project dependencies...
uv sync

if errorlevel 1 (
    echo [ERROR] Dependency sync failed.
    popd
    pause
    exit /b 1
)

echo [3/3] Done!
echo Environment is ready. You can now use Launch.bat to start AiNiee CLI.
popd
pause
