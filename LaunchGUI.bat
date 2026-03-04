@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AiNiee GUI Launcher

cd /d "%~dp0"

if not exist "Tools\WebServer\dist\index.html" (
    echo [ERROR] Tools\WebServer\dist\index.html not found.
    echo Build WebServer assets first:
    echo   cd Tools\WebServer
    echo   npm.cmd install
    echo   npm.cmd run build
    echo.
    pause
    exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
        set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    )
)

where uv >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Neither uv nor python is available.
        echo The prebuilt GUI needs one of them to start the local backend.
        echo.
        pause
        exit /b 1
    )
)

set "GUI_EXE=Tools\TauriShell\src-tauri\target\release\ainiee-tauri-shell.exe"

if exist "%GUI_EXE%" (
    echo Starting AiNiee GUI [prebuilt binary]...
    "%GUI_EXE%"
    set "EXIT_CODE=!ERRORLEVEL!"
    if not "!EXIT_CODE!"=="0" (
        echo.
        echo [ERROR] GUI exited with code !EXIT_CODE!.
    )
    pause
    exit /b !EXIT_CODE!
)

if /I not "%AINIEE_GUI_DEV%"=="1" (
    echo [ERROR] Prebuilt GUI binary not found:
    echo   %GUI_EXE%
    echo.
    echo No Node.js is required for end users, but you must provide a prebuilt binary.
    echo If you are developing locally, run this script with:
    echo   set AINIEE_GUI_DEV=1
    echo   LaunchGUI.bat
    echo.
    pause
    exit /b 1
)

where cargo >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
        set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    )
)

where cargo >nul 2>&1
if errorlevel 1 (
    echo [ERROR] cargo is not installed or not in PATH.
    echo Please install Rust toolchain first: https://rustup.rs/
    echo.
    pause
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm is not available.
    echo Please install Node.js first: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo [DEV] Starting Tauri dev mode...
pushd "Tools\TauriShell"
call npm.cmd install
if errorlevel 1 (
    echo [ERROR] npm install failed in Tools\TauriShell.
    popd
    pause
    exit /b 1
)
call npm.cmd run tauri:dev
set "EXIT_CODE=!ERRORLEVEL!"
popd
pause
exit /b !EXIT_CODE!
