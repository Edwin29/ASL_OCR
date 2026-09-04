@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE=%REPO_ROOT%\.venv-e0b\Scripts\python.exe"
set "DEFAULT_CONFIG_ROOT=D:\ASL_OCR_E0B"
set "CONFIG_ROOT=%DEFAULT_CONFIG_ROOT%"
set "PROFILE=%~2"

rem Allow the common shorthand `e0b-laptop-run.bat webcam`.
if not "%~1"=="" (
  if /I "%~1"=="webcam" (
    set "PROFILE=webcam"
  ) else if /I "%~1"=="webcame" (
    set "PROFILE=webcam"
    echo [E0-B] Corrected profile typo "webcame" to "webcam".
  ) else if /I "%~1"=="web-cam" (
    set "PROFILE=webcam"
  ) else if /I "%~1"=="web_cam" (
    set "PROFILE=webcam"
  ) else if /I "%~1"=="cam" (
    set "PROFILE=webcam"
  ) else (
    set "CONFIG_ROOT=%~f1"
  )
)

rem Correct the same aliases when a config root was supplied explicitly.
if /I "%PROFILE%"=="webcame" (
  set "PROFILE=webcam"
  echo [E0-B] Corrected profile typo "webcame" to "webcam".
)
if /I "%PROFILE%"=="web-cam" set "PROFILE=webcam"
if /I "%PROFILE%"=="web_cam" set "PROFILE=webcam"
if /I "%PROFILE%"=="cam" set "PROFILE=webcam"

if "%PROFILE%"=="" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.toml"
) else if /I "%PROFILE%"=="webcam" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.webcam.toml"
) else if /I "%PROFILE%"=="hardware" (
  set "APP_CONFIG=%CONFIG_ROOT%\device-app.e0b.hardware.toml"
) else (
  echo [E0-B] Unknown profile "%PROFILE%". Use webcam or hardware.
  exit /b 2
)

if not exist "%PYTHON_EXE%" (
  echo [E0-B] Environment not found. Run e0b-laptop-setup.bat first.
  exit /b 2
)
if not exist "%APP_CONFIG%" (
  set "REQUESTED_CONFIG=%APP_CONFIG%"
  if "%PROFILE%"=="" (
    set "FALLBACK_CONFIG=%DEFAULT_CONFIG_ROOT%\device-app.e0b.toml"
  ) else if /I "%PROFILE%"=="webcam" (
    set "FALLBACK_CONFIG=%DEFAULT_CONFIG_ROOT%\device-app.e0b.webcam.toml"
  ) else if /I "%PROFILE%"=="hardware" (
    set "FALLBACK_CONFIG=%DEFAULT_CONFIG_ROOT%\device-app.e0b.hardware.toml"
  )
  call :resolve_config_fallback
  if errorlevel 1 exit /b 2
)
"%PYTHON_EXE%" -m asl_device --config "%APP_CONFIG%"
exit /b %ERRORLEVEL%

:resolve_config_fallback
if defined FALLBACK_CONFIG if exist "%FALLBACK_CONFIG%" (
  echo [E0-B] Config not found at requested path: %REQUESTED_CONFIG%
  echo [E0-B] Falling back to: %FALLBACK_CONFIG%
  set "APP_CONFIG=%FALLBACK_CONFIG%"
  exit /b 0
)
echo [E0-B] Config not found: %REQUESTED_CONFIG%
echo [E0-B] Run e0b-laptop-setup.bat for this profile first.
exit /b 1
