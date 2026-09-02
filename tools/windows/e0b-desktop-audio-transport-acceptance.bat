@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%REPO_ROOT%\document-parser\.venv\Scripts\python.exe"

if "%~1"=="" goto :usage
if not exist "%PYTHON_EXE%" (
  echo [E0-B.4-D.1] No compatible repository Python environment was found.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
echo [E0-B.4-D.1] This test may play a short beep, low tone, and high tone.
echo [E0-B.4-D.1] Use --no-playback for automated transport checks without sound.
"%PYTHON_EXE%" "%SCRIPT_DIR%e0b_desktop_audio_transport_acceptance.py" %*
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<prepared-root^> [--no-playback] [--evidence-dir PATH] [--work-dir PATH]
echo Example: %~nx0 D:\ASL_OCR_E0B
exit /b 1
