$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'
$targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @('python.exe','powershell.exe')) -and
    (($_.CommandLine -like '*h3r-physical-down-harness.py*') -or ($_.CommandLine -like '*h3r-physical-down-runtime.ps1*'))
}
foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$files = @(
    (Join-Path $root 'logs\h3r-physical-down-console.log'),
    (Join-Path $root 'logs\h3r-physical-down-events.jsonl'),
    (Join-Path $root 'logs\h3r-physical-down-com5.jsonl'),
    (Join-Path $root 'manifests\h3r-physical-down-harness.py'),
    (Join-Path $root 'config\device-app.h3r-braille-only.toml')
)
$evidence = foreach ($file in $files) {
    if (Test-Path -LiteralPath $file) {
        $item = Get-Item -LiteralPath $file
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $file
        [pscustomobject]@{Path=$file; Length=$item.Length; SHA256=$hash.Hash}
    }
}
$evidence | ConvertTo-Json -Depth 3
Write-Output 'REMAINING_RUNTIME_PROCESSES'
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @('python.exe','powershell.exe')) -and
    (($_.CommandLine -like '*h3r-physical-down-harness.py*') -or ($_.CommandLine -like '*h3r-physical-down-runtime.ps1*'))
} | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3
