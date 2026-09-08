$ErrorActionPreference='Stop'
$name='ASL_OCR_H2_COM5Trace'
$script='C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639\manifests\com5-trace.py'
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$a=New-ScheduledTaskAction -Execute 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\pythonw.exe' -Argument ('"'+$script+'"')
$t=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddHours(1))
$p=New-ScheduledTaskPrincipal -UserId 'user' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $a -Trigger $t -Principal $p -Force|Out-Null
Start-ScheduledTask -TaskName $name

