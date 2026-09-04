@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
if "%~1"=="" (set "STATE_ROOT=D:\device-config\state\e0b-production") else (set "STATE_ROOT=%~f1")
if "%~2"=="" (set "REPORT=%STATE_ROOT%\reports\datapack-preflight.json") else (set "REPORT=%~f2")
if defined E0B_PRODUCTION_SERVER_PYTHON set "SERVER_PYTHON=%E0B_PRODUCTION_SERVER_PYTHON%"
if not defined SERVER_PYTHON set "SERVER_PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"

if not exist "%SERVER_PYTHON%" (
  echo [E0-B] Production Python not found: %SERVER_PYTHON%
  exit /b 2
)
if not exist "%STATE_ROOT%\server.sqlite3" (
  echo [E0-B] Server state database not found: %STATE_ROOT%\server.sqlite3
  exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
chcp 65001 >nul

"%SERVER_PYTHON%" -m document_parser.datapack.preflight ^
  --datapacks-dir "%STATE_ROOT%\datapacks" ^
  --state-db "%STATE_ROOT%\server.sqlite3" ^
  --report "%REPORT%"
set "RESULT=%ERRORLEVEL%"
echo [E0-B] Datapack preflight report: %REPORT%
exit /b %RESULT%
