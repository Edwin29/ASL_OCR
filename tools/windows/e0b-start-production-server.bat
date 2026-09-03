@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

if defined E0B_PRODUCTION_SERVER_PYTHON set "SERVER_PYTHON=%E0B_PRODUCTION_SERVER_PYTHON%"
if not defined SERVER_PYTHON set "SERVER_PYTHON=D:\venvs\gpu_ocr_test\Scripts\python.exe"
if defined E0B_PRODUCTION_MODEL_HOME set "MODEL_HOME=%E0B_PRODUCTION_MODEL_HOME%"
if not defined MODEL_HOME set "MODEL_HOME=D:\ASL_OCR_E0B\models\paddleocr-vl"
if defined E0B_PIPER_MODEL set "PIPER_MODEL=%E0B_PIPER_MODEL%"
if not defined PIPER_MODEL set "PIPER_MODEL=D:\models\piper-korean\ko_KR-kss-medium.onnx"
if defined E0B_PIPER_ESPEAK_DATA set "ESPEAK_DATA=%E0B_PIPER_ESPEAK_DATA%"
if not defined ESPEAK_DATA set "ESPEAK_DATA=D:\espeak-ng-data"
if defined E0B_DEVICE set "INFERENCE_DEVICE=%E0B_DEVICE%"
if not defined INFERENCE_DEVICE set "INFERENCE_DEVICE=gpu:0"

if "%~1"=="" (set "STATE_ROOT=D:\device-config\state\e0b-production") else (set "STATE_ROOT=%~f1")
if "%~2"=="" (set "API_KEY_FILE=D:\device-config\secrets\device-api-key.txt") else (set "API_KEY_FILE=%~f2")
if "%~3"=="" (set "PORT=8421") else (set "PORT=%~3")

if not exist "%SERVER_PYTHON%" (
  echo [E0-B-PROD] Production Python not found: %SERVER_PYTHON%
  exit /b 2
)
if not exist "%API_KEY_FILE%" (
  echo [E0-B-PROD] API key file not found: %API_KEY_FILE%
  exit /b 2
)
if not exist "%MODEL_HOME%\.paddlex\official_models\PP-DocLayoutV3" (
  echo [E0-B-PROD] PP-DocLayoutV3 model not found under: %MODEL_HOME%
  exit /b 2
)
if not exist "%MODEL_HOME%\.paddlex\official_models\PaddleOCR-VL-1.6" (
  echo [E0-B-PROD] PaddleOCR-VL-1.6 model not found under: %MODEL_HOME%
  exit /b 2
)
if not exist "%PIPER_MODEL%" (
  echo [E0-B-PROD] Piper model not found: %PIPER_MODEL%
  exit /b 2
)
if not exist "%PIPER_MODEL%.json" (
  echo [E0-B-PROD] Piper model config not found: %PIPER_MODEL%.json
  exit /b 2
)
if not exist "%ESPEAK_DATA%" (
  echo [E0-B-PROD] eSpeak data not found: %ESPEAK_DATA%
  exit /b 2
)

if not exist "%STATE_ROOT%\datapacks" mkdir "%STATE_ROOT%\datapacks"
if not exist "%STATE_ROOT%\jobs" mkdir "%STATE_ROOT%\jobs"

set "PYTHONPATH=%REPO_ROOT%\document-parser\src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
chcp 65001 >nul

echo [E0-B-PROD] Starting production PaddleOCR-VL/Piper Server.
echo [E0-B-PROD] Origin: http://127.0.0.1:%PORT%
echo [E0-B-PROD] State: %STATE_ROOT%
echo [E0-B-PROD] Device: %INFERENCE_DEVICE%
"%SERVER_PYTHON%" -m document_parser.server.combined_server ^
  --host 127.0.0.1 ^
  --port %PORT% ^
  --api-key-file "%API_KEY_FILE%" ^
  --datapacks-dir "%STATE_ROOT%\datapacks" ^
  --jobs-dir "%STATE_ROOT%\jobs" ^
  --state-db "%STATE_ROOT%\server.sqlite3" ^
  --model-home "%MODEL_HOME%" ^
  --device "%INFERENCE_DEVICE%" ^
  --piper-model "%PIPER_MODEL%" ^
  --piper-espeak-data "%ESPEAK_DATA%"
exit /b %ERRORLEVEL%
