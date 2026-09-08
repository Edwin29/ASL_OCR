$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8='1'
& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\manifests\h3r-braille-only-harness.py'