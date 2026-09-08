$ErrorActionPreference = 'Stop'
$taskName = 'ASL_OCR_H1_Fresh_20260908_101447'
$launcherPid = 19976
$process = Get-Process -Id $launcherPid -ErrorAction SilentlyContinue
if ($null -ne $process) {
    Stop-Process -Id $launcherPid
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
[ordered]@{
    stopped_owned_launcher_pid = $launcherPid
    removed_owned_task = $taskName
} | ConvertTo-Json
