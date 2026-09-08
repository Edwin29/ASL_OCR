$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8='1'
& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639\manifests\h2-console-stm-harness.py'

