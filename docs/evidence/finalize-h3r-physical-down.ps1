$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'
$taskNames = @('ASL_OCR_H3R_COM5', 'ASL_OCR_H3R_PhysicalDown')
foreach ($taskName in $taskNames) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
foreach ($taskName in $taskNames) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}
$files = @(
    (Join-Path $root 'logs\h3r-physical-down-console.log'),
    (Join-Path $root 'logs\h3r-physical-down-events.jsonl'),
    (Join-Path $root 'logs\h3r-physical-down-com5.jsonl'),
    (Join-Path $root 'manifests\h3r-physical-down-harness.py'),
    (Join-Path $root 'config\device-app.h3r-braille-only.toml')
)
foreach ($file in $files) {
    if (Test-Path -LiteralPath $file) {
        $item = Get-Item -LiteralPath $file
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $file
        [pscustomobject]@{Path=$file; Length=$item.Length; SHA256=$hash.Hash}
    }
}
Write-Output 'REMAINING_PROCESSES'
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*h3r-physical-down*' } |
    Select-Object ProcessId, Name, CommandLine
