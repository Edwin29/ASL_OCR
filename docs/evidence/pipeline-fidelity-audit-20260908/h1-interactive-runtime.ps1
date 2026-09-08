$ErrorActionPreference = 'Stop'
$runRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944'
$python = 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe'
$config = Join-Path $runRoot 'config\device-app.h1-camera-console.toml'
$transcript = Join-Path $runRoot 'logs\h1-interactive-console-transcript.txt'

$host.UI.RawUI.WindowTitle = 'ASL OCR H1 - Live Camera + Console'
Set-Location 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8 = '1'
Start-Transcript -LiteralPath $transcript -Append | Out-Null
Write-Host 'ASL OCR H1 live camera + console integration'
Write-Host 'Start in capture catalog. Commands: up/down/confirm, confirm long, lever activated, lever released.'
Write-Host 'Keep page 26/27 still until spread_sent and durable ACK appear; turn to 28/29 only when instructed.'
try {
    & $python -m asl_device --config $config --initial-mode capture
    $exitCode = $LASTEXITCODE
    Write-Host "Device runtime exited with code $exitCode"
}
finally {
    Stop-Transcript | Out-Null
}

