$ErrorActionPreference = 'Stop'
$taskName = 'ASL_OCR_H1_Fresh_20260908_101447'
$script = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447\launcher\h1-interactive-runtime.ps1'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "unique run task already exists: $taskName"
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoExit -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddHours(1))
$principal = New-ScheduledTaskPrincipal -UserId 'user' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 8
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
[ordered]@{
    task_name = $taskName
    state = [string]$task.State
    last_task_result = $info.LastTaskResult
    interactive_user = 'user'
} | ConvertTo-Json
