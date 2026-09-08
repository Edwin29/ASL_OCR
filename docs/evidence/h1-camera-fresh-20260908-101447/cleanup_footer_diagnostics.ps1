$ErrorActionPreference = 'Stop'
$taskNames = @(
    'ASL_OCR_H1_Footer30s_20260908_101447',
    'ASL_OCR_H1_FooterProd30s_20260908_101447',
    'ASL_OCR_H1_FooterProd30s02_20260908_101447',
    'ASL_OCR_H1_FooterProd30s03_20260908_101447'
)
$before = foreach ($taskName in $taskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        [ordered]@{
            task_name = $taskName
            state = [string]$task.State
            last_task_result = $info.LastTaskResult
            last_run_time_utc = $info.LastRunTime.ToUniversalTime().ToString('o')
        }
    }
}
$processes = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq 'python.exe' -and
            $_.CommandLine -like '*run_footer_30s_diagnostic.py*'
        } |
        Select-Object ProcessId, ParentProcessId, CommandLine
)
if ($processes.Count -ne 0) {
    throw 'diagnostic process still running; cleanup refused'
}
foreach ($taskName in $taskNames) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}
[ordered]@{
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    tasks_before_cleanup = @($before)
    diagnostic_processes_before_cleanup = @($processes)
    tasks_remaining = @(
        $taskNames | Where-Object {
            $null -ne (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue)
        }
    )
} | ConvertTo-Json -Depth 5
