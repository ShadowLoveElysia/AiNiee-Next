@echo off
setlocal
title AiNiee - Install Live Translation Extensions
pushd "%~dp0" >nul
if errorlevel 1 exit /b 1

set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
if defined UV_INSTALL_DIR set "PATH=%UV_INSTALL_DIR%;%PATH%"
uv --version
if errorlevel 1 (
    echo [ERROR] uv was not found. Install uv or run prepare.bat first.
    goto :failed
)

set "MEDIA_DEVICE=%~1"
if not defined MEDIA_DEVICE set "MEDIA_DEVICE=auto"
if "%MEDIA_DEVICE%"=="auto" goto :valid_device
if "%MEDIA_DEVICE%"=="cpu" goto :valid_device
if "%MEDIA_DEVICE%"=="cuda:0" goto :valid_device
if "%MEDIA_DEVICE%"=="vulkan" goto :valid_device
echo [ERROR] Device must be auto, cpu, cuda:0 or vulkan.
goto :failed

:valid_device
set "MEDIA_FAMILY=%~2"
set "MEDIA_PYTHON=%CD%\Resource\MediaRuntime\Scripts\python.exe"
set "MEDIA_PLAN=%CD%\tmp\test\test_media_install_plan.txt"
echo This installs live translation extensions into Resource\MediaRuntime.
echo Device: %MEDIA_DEVICE%. Model: saved controller selection, or index if unset.
echo Downloads may require several GB. Model weights are not downloaded.
echo Full installer errors will remain visible in this console.
echo.

echo [1/5] Preparing isolated Python 3.12...
if not exist "tmp\test" mkdir "tmp\test"
if errorlevel 1 goto :failed
if exist "%MEDIA_PYTHON%" goto :check_python
uv venv --python 3.12 --seed "Resource\MediaRuntime"
if errorlevel 1 goto :failed

:check_python
"%MEDIA_PYTHON%" -c "import sys,struct; print(sys.version); assert sys.version_info[:2] == (3,12), 'Media runtime needs Python 3.12'; assert struct.calcsize('P') == 8, 'Media runtime needs 64-bit Python'"
if errorlevel 1 goto :failed
"%MEDIA_PYTHON%" Tools\Bootstrap\prepare_media_runtime.py plan --device "%MEDIA_DEVICE%" --family "%MEDIA_FAMILY%" > "%MEDIA_PLAN%"
if errorlevel 1 (
    type "%MEDIA_PLAN%"
    goto :failed
)
type "%MEDIA_PLAN%"
set "MEDIA_BUILD="
for /f "skip=1 delims=" %%A in ('type "%MEDIA_PLAN%"') do if not defined MEDIA_BUILD set "MEDIA_BUILD=%%A"
for /f "skip=2 delims=" %%A in ('type "%MEDIA_PLAN%"') do set "MEDIA_FAMILY=%%A"
if "%MEDIA_BUILD%"=="cuda" goto :cuda
if not "%MEDIA_BUILD%"=="cpu" goto :failed
set "MEDIA_TORCH_INDEX=https://download.pytorch.org/whl/cpu"
set "MEDIA_TORCH_SUFFIX=+cpu"
goto :install_torch

:cuda
set "MEDIA_TORCH_INDEX=https://download.pytorch.org/whl/cu126"
set "MEDIA_TORCH_SUFFIX=+cu126"

:install_torch
echo [2/5] Installing matching Torch and torchaudio builds...
uv pip install --python "%MEDIA_PYTHON%" --index-url "%MEDIA_TORCH_INDEX%" "torch==2.9.1%MEDIA_TORCH_SUFFIX%" "torchaudio==2.9.1%MEDIA_TORCH_SUFFIX%"
if errorlevel 1 goto :failed

echo [3/5] Installing ASR, translation and audio extensions...
uv pip install --python "%MEDIA_PYTHON%" --index-url https://pypi.org/simple "transformers==5.6.0" accelerate "funasr>=1.2,<2" sentencepiece silero-vad onnxruntime soundcard numpy soundfile librosa huggingface-hub safetensors requests
if errorlevel 1 goto :failed

echo [4/5] Preparing the selected inference backend...
"%MEDIA_PYTHON%" -u -m ModuleFolders.Media.runtime configure --device "%MEDIA_DEVICE%" --family "%MEDIA_FAMILY%"
if errorlevel 1 goto :failed

echo [5/5] Verifying installed extensions and device availability...
"%MEDIA_PYTHON%" Tools\Bootstrap\prepare_media_runtime.py verify --device "%MEDIA_DEVICE%" --family "%MEDIA_FAMILY%"
if errorlevel 1 goto :failed
echo.
echo Environment is ready. Reopen the controller and click Check environment.
echo The verified runtime Python has been saved for the controller.
popd
pause
exit /b 0

:failed
echo.
echo [ERROR] Live translation setup failed. Copy the error lines above for diagnosis.
echo If CUDA is unavailable, select CPU explicitly: prepare_media.bat cpu
popd
pause
exit /b 1
