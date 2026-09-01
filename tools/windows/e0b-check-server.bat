@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\document-parser\.venv\Scripts\python.exe"
set "HEALTH_SCRIPT=%SCRIPT_DIR%e0b_health_check.py"

if "%~1"=="" (
  set "SERVER_ORIGIN=http://127.0.0.1:8421"
) else (
  set "SERVER_ORIGIN=%~1"
)

if "%SERVER_ORIGIN:~-1%"=="/" set "SERVER_ORIGIN=%SERVER_ORIGIN:~0,-1%"
if not exist "%PYTHON_EXE%" (
  echo [E0-B] Python environment not found: "%PYTHON_EXE%"
  exit /b 2
)
if not exist "%HEALTH_SCRIPT%" (
  echo [E0-B] Health helper not found: "%HEALTH_SCRIPT%"
  exit /b 2
)

echo [E0-B] Checking %SERVER_ORIGIN%/api/v1/health
"%PYTHON_EXE%" "%HEALTH_SCRIPT%" "%SERVER_ORIGIN%"
if errorlevel 1 (
  echo [E0-B] Health check failed.
  exit /b 1
)
echo [E0-B] Health check passed.
exit /b 0
