@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%REPO_ROOT%\document-parser\.venv\Scripts\python.exe"

if "%~1"=="" goto :usage
if not exist "%PYTHON_EXE%" (
  echo [E0-B.4-D] No compatible repository Python environment was found.
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\device-runtime\src;%REPO_ROOT%\book-scanner\src;%REPO_ROOT%\document-parser\src"
echo [E0-B.4-D] Desktop loopback evidence is not Laptop, Tailscale, or physical acceptance.
"%PYTHON_EXE%" "%SCRIPT_DIR%e0b_desktop_loopback_acceptance.py" %*
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<prepared-root^> [--evidence-dir PATH] [--work-dir PATH]
echo Example: %~nx0 D:\ASL_OCR_E0B
exit /b 1
