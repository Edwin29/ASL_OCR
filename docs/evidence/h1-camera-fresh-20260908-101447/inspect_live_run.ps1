$ErrorActionPreference = 'Stop'
$runRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447'
$processes = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m asl_device*' } |
    Select-Object ProcessId, ParentProcessId, CommandLine
$processStats = Get-Process -Id @($processes.ProcessId) -ErrorAction SilentlyContinue |
    Select-Object Id, CPU, WorkingSet64, StartTime, Responding
$lifecycle = Get-Content -LiteralPath (Join-Path $runRoot 'evidence\interactive-lifecycle.json') -Raw | ConvertFrom-Json
$stateFiles = Get-ChildItem -LiteralPath (Join-Path $runRoot 'state') -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTimeUtc
[ordered]@{
    processes = @($processes)
    process_stats = @($processStats)
    lifecycle = $lifecycle
    state_files = @($stateFiles)
} | ConvertTo-Json -Depth 5
