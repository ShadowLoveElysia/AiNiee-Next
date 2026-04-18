@echo off
setlocal
title AiNiee CLI
pushd "%~dp0" >nul

uv --version >nul 2>&1
if errorlevel 1 (
    REM Check if it was just installed and in the default cargo path
    if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
        set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    ) else (
        echo [ERROR] uv is not installed or not in PATH.
        echo Please run 'prepare.bat' first to set up the environment.
        echo.
        popd
        pause
        exit /b 1
    )
)

REM Keep the Windows runtime away from the WSL/Linux project .venv.
REM A Linux-created .venv often contains lib64 symlinks that uv cannot
REM clean up correctly when started from Windows.
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv-win"

if exist ".venv\lib64" (
    echo [INFO] Detected a non-Windows .venv. Using "%UV_PROJECT_ENVIRONMENT%" for this launch.
)

echo Starting AiNiee CLI...
uv run ainiee_cli.py

set "EXIT_CODE=%errorlevel%"
popd
pause
exit /b %EXIT_CODE%
