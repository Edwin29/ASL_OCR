$ErrorActionPreference = 'Stop'
$runRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\audio-console-20260908-163539'
$python = 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe'
$harness = Join-Path $runRoot 'launcher\audio_console_harness.py'
$transcript = Join-Path $runRoot 'logs\audio-console-transcript.txt'

$host.UI.RawUI.WindowTitle = 'ASL OCR Audio 1B 20260908-163539'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8 = '1'
Start-Transcript -LiteralPath $transcript -Append | Out-Null
Write-Host 'ASL OCR 1B: existing READY + console + authenticated Piper/system audio + Laptop speaker'
Write-Host 'Commands will be provided step by step. Do not enter rapid sequences before instruction.'
try {
    & $python $harness
    $exitCode = $LASTEXITCODE
    Write-Host "1B runtime exited with code $exitCode"
}
finally {
    Stop-Transcript | Out-Null
}
