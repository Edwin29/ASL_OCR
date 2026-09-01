@echo off
setlocal EnableExtensions DisableDelayedExpansion

if "%~1"=="" goto :usage
set "SCRIPT_DIR=%~dp0"
set "REPLAY_VIDEO=%~f1"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%e0b-laptop-setup.ps1" -ReplayVideo "%REPLAY_VIDEO%" -SkipPreflight
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo [E0-B.1] Replay setup failed with exit code %RESULT%.
) else (
  echo [E0-B.1] Replay setup completed.
)
if /I "%E0B_NO_PAUSE%"=="1" exit /b %RESULT%
pause
exit /b %RESULT%

:usage
echo Usage: %~nx0 ^<prepared-video.mp4^>
echo Example: %~nx0 D:\Downloads\acceptance.mp4
exit /b 1
