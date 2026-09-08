$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'
Write-Output 'TASK'
Get-ScheduledTask -TaskName 'ASL_OCR_H3R_PhysicalDown' -ErrorAction SilentlyContinue |
    Get-ScheduledTaskInfo |
    Format-List LastRunTime, LastTaskResult, TaskName, TaskPath
Write-Output 'PROCESSES'
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*h3r-physical-down*' } |
    Select-Object ProcessId, Name, CommandLine |
    Format-List
Write-Output 'CONSOLE_TAIL'
$consoleLog = Join-Path $root 'logs\h3r-physical-down-console.log'
if (Test-Path -LiteralPath $consoleLog) {
    Get-Content -LiteralPath $consoleLog -Tail 100
}
Write-Output 'EVENT_TAIL'
$eventLog = Join-Path $root 'logs\h3r-physical-down-events.jsonl'
if (Test-Path -LiteralPath $eventLog) {
    Get-Content -LiteralPath $eventLog -Tail 40
}
