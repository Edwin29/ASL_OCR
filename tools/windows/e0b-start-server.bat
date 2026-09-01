@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\document-parser\.venv\Scripts\python.exe"

if "%~1"=="" goto :usage
set "API_KEY_FILE=%~f1"
if not exist "%API_KEY_FILE%" (
  echo [E0-B] API key file not found: "%API_KEY_FILE%"
  exit /b 2
)

if "%~2"=="" (
  set "STATE_ROOT=%REPO_ROOT%\tmp\e0b-desktop-server"
) else (
  set "STATE_ROOT=%~f2"
)

if not exist "%PYTHON_EXE%" (
  echo [E0-B] Python environment not found: "%PYTHON_EXE%"
  echo [E0-B] Create document-parser\.venv and install document-parser[remote-ingest].
  exit /b 3
)

set "PYTHONPATH=%REPO_ROOT%\document-parser\src"
echo [E0-B] Starting desktop Server origin at http://127.0.0.1:8421
echo [E0-B] State root: "%STATE_ROOT%"
"%PYTHON_EXE%" -m document_parser.server.e0b_bench_server ^
  --host 127.0.0.1 ^
  --port 8421 ^
  --state-root "%STATE_ROOT%" ^
  --api-key-file "%API_KEY_FILE%"
exit /b %ERRORLEVEL%

:usage
echo Usage: %~nx0 ^<api-key-file^> [state-root]
echo Example: %~nx0 D:\device-config\secrets\device-api-key.txt D:\device-config\state\e0b-bench
exit /b 1
