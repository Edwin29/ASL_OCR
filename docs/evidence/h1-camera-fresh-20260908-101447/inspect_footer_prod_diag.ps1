$ErrorActionPreference = 'Stop'
$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447'
$taskName = 'ASL_OCR_H1_FooterProd30s_20260908_101447'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$info = if ($null -ne $task) { Get-ScheduledTaskInfo -TaskName $taskName } else { $null }
$files = Get-ChildItem -LiteralPath (Join-Path $root 'evidence\footer-30s-production-input-01') -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTimeUtc
$processes = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_footer_30s_diagnostic.py*' } |
    Select-Object ProcessId, ParentProcessId, CommandLine
[ordered]@{
    task_state = if ($null -ne $task) { [string]$task.State } else { $null }
    last_task_result = if ($null -ne $info) { $info.LastTaskResult } else { $null }
    last_run_time = if ($null -ne $info) { $info.LastRunTime.ToUniversalTime().ToString('o') } else { $null }
    files = @($files)
    processes = @($processes)
} | ConvertTo-Json -Depth 5
