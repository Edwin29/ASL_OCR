@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
if "%~1"=="" (set "CONFIG_ROOT=D:\ASL_OCR_E0B") else (set "CONFIG_ROOT=%~f1")

echo [E0-B.1] Console controls: up, down, left, right, next, prev, confirm, lever [short^|long^|activated^|released]
echo [E0-B.1] Stop the process with Ctrl+C after the final reading check.
echo [E0-B.1] Reading snapshots are emitted as JSON lines with cursor, braille_cells, and audio_ref.
echo [E0-B.2] At scan_input_exhausted, wait for spread_sent if queued_count is nonzero, then enter confirm.
echo [E0-B.2] If queued_count is zero, the replay acceptance failed; stop with Ctrl+C and keep the log.
call "%SCRIPT_DIR%e0b-laptop-run.bat" "%CONFIG_ROOT%"
exit /b %ERRORLEVEL%
