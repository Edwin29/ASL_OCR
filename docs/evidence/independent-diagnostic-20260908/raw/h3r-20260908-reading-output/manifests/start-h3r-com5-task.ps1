$taskName = 'ASL_OCR_H3R_COM5'
$manifest = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\manifests'
$wrapper = Join-Path $manifest 'h3r-com5-physical-down-runtime.ps1'
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $wrapper)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo | Format-List LastRunTime,LastTaskResult
