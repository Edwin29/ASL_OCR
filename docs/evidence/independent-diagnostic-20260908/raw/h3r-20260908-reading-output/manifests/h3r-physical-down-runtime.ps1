Stop='Continue'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
='1'
& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\manifests\h3r-physical-down-harness.py' 2>&1 | Tee-Object -FilePath 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\logs\h3r-physical-down-console.log' -Append