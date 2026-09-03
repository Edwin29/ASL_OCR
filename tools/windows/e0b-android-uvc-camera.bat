@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo [ANDROID-UVC] FAILED: Environment not found at %PYTHON_EXE%.
  echo [ANDROID-UVC] Run tools\windows\e0b-replay-setup.bat or e0b-laptop-setup.bat first.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%PYTHONPATH%"
"%PYTHON_EXE%" "%REPO_ROOT%\tools\windows\e0b_android_uvc_camera.py" %*
exit /b %ERRORLEVEL%
