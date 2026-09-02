@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
if "%~1"=="" goto :usage

if defined E0B_PRODUCTION_SERVER_PYTHON set "OCR_PYTHON=%E0B_PRODUCTION_SERVER_PYTHON%"
if not defined OCR_PYTHON if exist "D:\venvs\gpu_ocr_test\Scripts\python.exe" set "OCR_PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"
if not defined OCR_PYTHON (
  echo [E0-B.5-D.1] No production PaddleOCR-VL Python was found.
  exit /b 2
)
if defined E0B_DEVICE_PYTHON set "SCANNER_PYTHON=%E0B_DEVICE_PYTHON%"
if not defined SCANNER_PYTHON if exist "%REPO_ROOT%\.venv-e0b\Scripts\python.exe" set "SCANNER_PYTHON=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if not defined SCANNER_PYTHON (
  echo [E0-B.5-D.1] No prepared Book Scanner Python was found.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\book-scanner\src;%REPO_ROOT%\document-parser\src"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
echo [E0-B.5-D.1] p030 only: frame 780, left page, UVDoc, real PaddleOCR-VL, human-golden comparison.
echo [E0-B.5-D.1] No TTS, playback, server write, or model download is allowed.
"%OCR_PYTHON%" "%REPO_ROOT%\book-scanner\tools\run_p030_mp4_production_diagnostic.py" "%~1" --scanner-python "%SCANNER_PYTHON%" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<prepared-root^> [--device gpu:0^|cpu] [--output-dir PATH]
echo Example: %~nx0 D:\ASL_OCR_E0B
exit /b 1
