@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%e0b-laptop-setup.ps1" %*
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo [E0-B] Laptop setup failed with exit code %RESULT%.
) else (
  echo [E0-B] Laptop setup completed.
)
if /I "%E0B_NO_PAUSE%"=="1" exit /b %RESULT%
pause
exit /b %RESULT%
