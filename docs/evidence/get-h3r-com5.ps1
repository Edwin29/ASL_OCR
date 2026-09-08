$root='C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'
$log=Join-Path $root 'logs\h3r-physical-down-com5.jsonl'
Write-Output 'COM5_TASK'
Get-ScheduledTask -TaskName 'ASL_OCR_H3R_COM5' -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List LastRunTime,LastTaskResult
Write-Output 'COM5_LOG'
if(Test-Path -LiteralPath $log){Get-Content -LiteralPath $log -Tail 80; Get-FileHash -Algorithm SHA256 -LiteralPath $log | Format-List Algorithm,Hash,Path}else{Write-Output 'MISSING'}
