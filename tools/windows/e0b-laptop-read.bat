@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if "%~1"=="" (set "CONFIG_ROOT=D:\ASL_OCR_E0B") else (set "CONFIG_ROOT=%~f1")
set "PROFILE=%~2"

if "%PROFILE%"=="" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.webcam.toml"
) else if /I "%PROFILE%"=="webcam" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.webcam.toml"
) else if /I "%PROFILE%"=="hardware" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.hardware.toml"
) else if /I "%PROFILE%"=="android-uvc" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.android-uvc.toml"
) else (
  echo [E0-B-READ] Unknown profile "%PROFILE%". Use webcam, hardware, or android-uvc.
  exit /b 2
)

if not exist "%PYTHON_EXE%" (
  echo [E0-B-READ] Environment not found. Run e0b-laptop-setup.bat first.
  exit /b 2
)
if not exist "%APP_CONFIG%" (
  echo [E0-B-READ] Config not found: %APP_CONFIG%
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%PYTHONPATH%"
echo [E0-B-READ] Starting directly in reading mode. No lever/jumper input is required.
"%PYTHON_EXE%" -m asl_device --config "%APP_CONFIG%" --initial-mode reading
exit /b %ERRORLEVEL%
