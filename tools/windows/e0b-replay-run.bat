@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
if "%~1"=="" (set "CONFIG_ROOT=D:\ASL_OCR_E0B") else (set "CONFIG_ROOT=%~f1")

echo [E0-B.1] Console controls: up, down, left, right, next, prev, confirm, lever [short^|long^|activated^|released]
echo [E0-B.1] Stop the process with Ctrl+C after the final reading check.
echo [E0-B.1] Reading snapshots are emitted as JSON lines with cursor, braille_cells, and audio_ref.
echo [E0-B.2] At scan_input_exhausted, wait for spread_sent if queued_count is nonzero, then enter confirm.
echo [E0-B.2] If queued_count is zero, the replay acceptance failed; stop with Ctrl+C and keep the log.
echo [E0-B.3] Stable candidate and transmitted spread are separate decisions; identity requires 5 later valid observations.
echo [E0-B.3] For the pinned test1.mp4, expect spread_sent 1,2 and scan_input_exhausted queued_count=2, acked_count=2.
echo [E0-B.3] candidate_selected and identity_collection_* feedback explain conservative rejections without changing them.
call "%SCRIPT_DIR%e0b-laptop-run.bat" "%CONFIG_ROOT%"
exit /b %ERRORLEVEL%
