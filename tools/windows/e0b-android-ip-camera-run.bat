@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
set "CONFIG_ROOT=%~f1"
if "%~1"=="" set "CONFIG_ROOT=D:\ASL_OCR_E0B"
set "CONFIG=%CONFIG_ROOT%\device-app.android-ip-camera.toml"

if not exist "%PYTHON_EXE%" (
  echo [ANDROID-IP-CAMERA] FAILED: Environment not found at %PYTHON_EXE%.
  exit /b 2
)
if not exist "%CONFIG%" (
  echo [ANDROID-IP-CAMERA] FAILED: Config not found at %CONFIG%.
  echo [ANDROID-IP-CAMERA] Copy device-runtime\device-app.android-ip-camera.example.toml and set the phone URL.
  exit /b 2
)

echo [ANDROID-IP-CAMERA] Full-resolution phone JPEG snapshots. No PC-camera fallback is enabled.
"%PYTHON_EXE%" -m asl_device --config "%CONFIG%"
exit /b %ERRORLEVEL%
