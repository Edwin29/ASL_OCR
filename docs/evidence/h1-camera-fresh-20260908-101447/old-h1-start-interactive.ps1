$ErrorActionPreference = 'Stop'
$taskName = 'ASL_OCR_H1_LiveCameraConsole'
$script = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944\manifests\h1-interactive-runtime.ps1'

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoExit -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddHours(1))
$principal = New-ScheduledTaskPrincipal -UserId 'user' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
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

