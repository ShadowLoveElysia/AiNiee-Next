@echo off
setlocal
title AiNiee CLI - Prepare Comic Runtime
pushd "%~dp0" >nul

set "BACKEND=%~1"
if /I "%BACKEND%"=="cpu" goto backend_ok
if /I "%BACKEND%"=="gpu" goto backend_ok
if /I "%BACKEND%"=="metal" goto backend_ok
if "%BACKEND%"=="" (
    set "BACKEND=cpu"
    goto backend_ok
)

echo [ERROR] Unsupported backend: %BACKEND%
echo Usage: prepare_comic.bat [cpu^|gpu^|metal]
popd
pause
exit /b 1

:backend_ok
set "REQUIREMENTS_FILE="
if /I "%BACKEND%"=="cpu" set "REQUIREMENTS_FILE=ModuleFolders\MangaCore\runtime\requirements_cpu.txt"
if /I "%BACKEND%"=="gpu" set "REQUIREMENTS_FILE=ModuleFolders\MangaCore\runtime\requirements_gpu.txt"
if /I "%BACKEND%"=="metal" set "REQUIREMENTS_FILE=ModuleFolders\MangaCore\runtime\requirements_metal.txt"

if not exist "%REQUIREMENTS_FILE%" (
    echo [ERROR] Missing requirements file: %REQUIREMENTS_FILE%
    popd
    pause
    exit /b 1
)

if not exist "ModuleFolders\MangaCore\runtime" (
    echo [ERROR] ModuleFolders\MangaCore\runtime is missing from the project root.
    popd
    pause
    exit /b 1
)

set "MANGA_VENV=%CD%\.venv-win-manga"
set "MANGA_PYTHON=%MANGA_VENV%\Scripts\python.exe"

echo [1/4] Checking for uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo uv not found. Starting automatic installation...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

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

echo [2/4] Creating manga runtime environment...
uv venv "%MANGA_VENV%" --python 3.12 --allow-existing
if errorlevel 1 (
    echo [ERROR] Failed to create manga runtime environment.
    popd
    pause
    exit /b 1
)

echo [3/4] Installing manga runtime dependencies (%BACKEND%)...
uv pip install --python "%MANGA_PYTHON%" -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to install manga runtime dependencies.
    popd
    pause
    exit /b 1
)

echo [4/4] Downloading default MangaCore model assets...
"%MANGA_PYTHON%" "%CD%\ModuleFolders\MangaCore\runtime\prepare_models.py"
if errorlevel 1 (
    echo [ERROR] Failed to download default MangaCore model assets.
    popd
    pause
    exit /b 1
)

echo [Done] Manga runtime environment is ready at "%MANGA_VENV%"
echo Main CLI dependencies are still managed by prepare.bat
popd
pause
exit /b 0
