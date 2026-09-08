$taskNames = @('ASL_OCR_H3R_PhysicalDown', 'ASL_OCR_H3R_COM5')
$tasks = foreach ($taskName in $taskNames) {
    Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue |
        Select-Object TaskName, State
}
$processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like '*h3r-physical-down-harness.py*') -or
    ($_.CommandLine -like '*h3r-com5-physical-down-logger.py*')
} | Select-Object ProcessId, Name, CommandLine
[pscustomobject]@{
    task_count = @($tasks).Count
    process_count = @($processes).Count
    tasks = @($tasks)
    processes = @($processes)
} | ConvertTo-Json -Depth 5
