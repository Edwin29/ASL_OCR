@echo off
setlocal
set "REPO=%~dp0..\.."
set "PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"

if "%~3"=="" (
  echo Usage: %~nx0 PREPARED_ROOT WORK_DIR DATAPACK_ID
  exit /b 2
)
if not exist "%PYTHON%" (
  echo [E0-B.5-D-AUDIO] FAILED: production Python was not found at %PYTHON%
  exit /b 2
)

set "PYTHONPATH=%REPO%\device-runtime\src;%REPO%\document-parser\src;%PYTHONPATH%"
echo [E0-B.5-D-AUDIO] Reusing an existing production revision; OCR will not run again.
"%PYTHON%" "%REPO%\tools\windows\e0b_production_audio_replay.py" "%~1" "%~2" "%~3"
exit /b %ERRORLEVEL%
