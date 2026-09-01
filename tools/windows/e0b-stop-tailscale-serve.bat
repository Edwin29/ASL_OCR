@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%e0b-stop-tailscale-serve.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [E0-B.1] Tailscale Serve stop failed with exit code %RESULT%.
if /I "%E0B_NO_PAUSE%"=="1" exit /b %RESULT%
pause
exit /b %RESULT%
