@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if "%~1"=="" (set "CONFIG_ROOT=D:\ASL_OCR_E0B") else (set "CONFIG_ROOT=%~f1")

if not exist "%PYTHON_EXE%" (
  echo [E0-B] Environment not found. Run e0b-laptop-setup.bat first.
  exit /b 2
)
"%PYTHON_EXE%" -m asl_device --config "%CONFIG_ROOT%\device-app.e0b.toml" --preflight --report "%CONFIG_ROOT%\reports\e0b-preflight.json"
exit /b %ERRORLEVEL%
