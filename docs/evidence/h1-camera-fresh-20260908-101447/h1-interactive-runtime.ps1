$ErrorActionPreference = 'Stop'
$runRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447'
$python = 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe'
$config = Join-Path $runRoot 'config\device-app.h1-camera-console.toml'
$transcript = Join-Path $runRoot 'logs\h1-interactive-console-transcript.txt'
$lifecycle = Join-Path $runRoot 'evidence\interactive-lifecycle.json'

$host.UI.RawUI.WindowTitle = 'ASL OCR Fresh H1 20260908-101447'
Set-Location 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8 = '1'

$sessionId = (Get-Process -Id $PID).SessionId
$started = (Get-Date).ToUniversalTime().ToString('o')
[ordered]@{
    state = 'starting'
    started_at_utc = $started
    powershell_pid = $PID
    windows_session_id = $sessionId
    source_root = 'C:\ASL_OCR_INTEGRATION'
    python = $python
    config = $config
    entrypoint = 'python -m asl_device'
    initial_mode = 'capture'
} | ConvertTo-Json | Set-Content -LiteralPath $lifecycle -Encoding utf8

Start-Transcript -LiteralPath $transcript -Append | Out-Null
Write-Host 'ASL OCR fresh H1: Android camera + production runtime + console controls'
Write-Host 'Commands: up, down, confirm, confirm long. Wait for operator instruction before each capture transition.'
Write-Host 'No STM packet is expected in this run because console controls are the approved H1 substitution.'
$exitCode = $null
try {
    & $python -m asl_device --config $config --initial-mode capture
    $exitCode = $LASTEXITCODE
    Write-Host "Device runtime exited with code $exitCode"
}
finally {
    [ordered]@{
        state = 'exited'
        started_at_utc = $started
        completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        powershell_pid = $PID
        windows_session_id = $sessionId
        exit_code = $exitCode
    } | ConvertTo-Json | Set-Content -LiteralPath $lifecycle -Encoding utf8
    Stop-Transcript | Out-Null
}
