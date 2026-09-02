@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
if "%~1"=="" goto :usage

if defined E0B_PIPER_PYTHON set "PYTHON_EXE=%E0B_PIPER_PYTHON%"
if not defined PYTHON_EXE if exist "D:\venvs\gpu_ocr_test\Scripts\python.exe" set "PYTHON_EXE=D:\venvs\gpu_ocr_test\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO_ROOT%\document-parser\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO_ROOT%\document-parser\.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  echo [E0-B.4-D.3] No Python environment was found. Set E0B_PIPER_PYTHON.
  exit /b 2
)
"%PYTHON_EXE%" -c "import piper" >nul 2>&1
if errorlevel 1 (
  echo [E0-B.4-D.3] The selected Python needs piper-tts.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
echo [E0-B.4-D.3] This test synthesizes real Korean Piper audio and may use the default speaker.
echo [E0-B.4-D.3] It checks navigation interruption, latest generation, and bounded RAM cache.
echo [E0-B.4-D.3] Use --no-playback for automated checks without sound.
"%PYTHON_EXE%" "%SCRIPT_DIR%e0b_device_audio_playback_acceptance.py" %*
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<prepared-root^> [--no-playback] [--piper-model PATH] [--piper-espeak-data PATH]
echo Example: %~nx0 D:\ASL_OCR_E0B
exit /b 1
