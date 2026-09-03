@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if "%~1"=="" (set "PREPARED_ROOT=D:\ASL_OCR_E0B") else (set "PREPARED_ROOT=%~f1")
set "CONFIG=%PREPARED_ROOT%\device-app.android-uvc.toml"

if not exist "%PYTHON_EXE%" (
  echo [ANDROID-UVC] FAILED: Environment not found at %PYTHON_EXE%.
  exit /b 2
)
if not exist "%CONFIG%" (
  echo [ANDROID-UVC] FAILED: Config not found at %CONFIG%.
  echo [ANDROID-UVC] Follow docs\ANDROID_UVC_CAMERA_HOST_RUNBOOK.md first.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%PYTHONPATH%"
echo [ANDROID-UVC] Live Android camera input. No MP4 fallback is enabled.
"%PYTHON_EXE%" -m asl_device --config "%CONFIG%"
exit /b %ERRORLEVEL%
