@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AiNiee Skills Server
pushd "%~dp0\..\.." >nul

where uv >nul 2>&1
if not errorlevel 1 (
    echo [Skills] Starting AiNiee Skills Server with uv...
    uv run python Tools\Skills\server.py %*
    set "EXIT_CODE=!errorlevel!"
    popd
    exit /b !EXIT_CODE!
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Neither uv nor python is available.
    echo Please run prepare.bat first or install Python 3.12.
    popd
    exit /b 1
)

echo [Skills] Starting AiNiee Skills Server with python...
python Tools\Skills\server.py %*
set "EXIT_CODE=!errorlevel!"
popd
exit /b !EXIT_CODE!
