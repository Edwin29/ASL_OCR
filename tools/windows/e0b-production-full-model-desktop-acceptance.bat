@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
if "%~1"=="" goto :usage

if defined E0B_PRODUCTION_SERVER_PYTHON set "SERVER_PYTHON=%E0B_PRODUCTION_SERVER_PYTHON%"
if not defined SERVER_PYTHON if exist "D:\venvs\gpu_ocr_test\Scripts\python.exe" set "SERVER_PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"
if not defined SERVER_PYTHON if exist "D:\venvs\paddleocr-vl\Scripts\python.exe" set "SERVER_PYTHON=D:\venvs\paddleocr-vl\Scripts\python.exe"
if not defined SERVER_PYTHON (
  echo [E0-B.5-D] No production Server Python was found. Set E0B_PRODUCTION_SERVER_PYTHON.
  exit /b 2
)

if defined E0B_DEVICE_PYTHON set "DEVICE_PYTHON=%E0B_DEVICE_PYTHON%"
if not defined DEVICE_PYTHON if exist "%REPO_ROOT%\.venv-e0b\Scripts\python.exe" set "DEVICE_PYTHON=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if not defined DEVICE_PYTHON set "DEVICE_PYTHON=%SERVER_PYTHON%"

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
chcp 65001 >nul

echo [E0-B.5-D] Pinned MP4 - real PaddleOCR-VL - real Piper - S0 - Device playback.
echo [E0-B.5-D] This is Desktop production-model evidence, not live-camera or STM/Pi evidence.
echo [E0-B.5-D] Without --no-playback, the run asks four listening questions after processing.
"%SERVER_PYTHON%" "%SCRIPT_DIR%e0b_production_full_model_desktop_acceptance.py" "%~1" --server-python "%SERVER_PYTHON%" --device-python "%DEVICE_PYTHON%" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<prepared-root^> [--model-home PATH] [--device gpu:0^|cpu] [--no-playback]
echo Example: %~nx0 D:\ASL_OCR_E0B --model-home D:\ASL_OCR_E0B\models\paddleocr-vl
exit /b 1
