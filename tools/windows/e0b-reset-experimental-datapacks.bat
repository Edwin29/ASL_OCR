@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

if defined E0B_PRODUCTION_SERVER_PYTHON set "SERVER_PYTHON=%E0B_PRODUCTION_SERVER_PYTHON%"
if not defined SERVER_PYTHON set "SERVER_PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"
if "%~1"=="" (set "STATE_ROOT=D:\device-config\state\e0b-production") else (set "STATE_ROOT=%~f1")
if "%~2"=="" goto :usage
set "CONFIRM_TOKEN=%~2"
if "%~3"=="" (set "HEALTH_URL=http://127.0.0.1:8421/api/v1/health") else (set "HEALTH_URL=%~3")

if not exist "%SERVER_PYTHON%" (
  echo [E0-B-RESET] Production Python not found: %SERVER_PYTHON%
  exit /b 2
)
if not exist "%STATE_ROOT%\" (
  echo [E0-B-RESET] State root not found: %STATE_ROOT%
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
chcp 65001 >nul
"%SERVER_PYTHON%" -m document_parser.server.experimental_reset ^
  --state-root "%STATE_ROOT%" ^
  --confirm "%CONFIRM_TOKEN%" ^
  --health-url "%HEALTH_URL%"
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 [state-root] RESET-E0B-EXPERIMENT [local-health-url]
echo Stop the production Server first. Existing state is moved to a recoverable sibling backup.
exit /b 1
