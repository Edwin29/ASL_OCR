$ErrorActionPreference='Continue'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8='1'
& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' -m asl_device --config 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3-20260908-001800\config\device-app.stm-reading.toml' 2>&1 | Tee-Object -FilePath 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3-20260908-001800\logs\h3-events-resumed.log' -Append