param(
    [Parameter(Mandatory = $true)] [string] $Elf,
    [Parameter(Mandatory = $true)] [string] $EvidenceRoot,
    [Parameter(Mandatory = $true)] [string] $Programmer,
    [Parameter(Mandatory = $true)] [ValidateSet("diagnostic", "candidate", "aligned", "production_restore")] [string] $Purpose,
    [string] $ProbeSerial = "0670FF485775495067203341"
)

$ErrorActionPreference = "Stop"
$approvedRoot = "C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\"
if (-not $Elf.StartsWith($approvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "ELF is outside the approved C: integration evidence runtime"
}
if (-not $EvidenceRoot.StartsWith($approvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "EvidenceRoot is outside the approved C: integration evidence runtime"
}
if (-not (Test-Path -LiteralPath $Elf -PathType Leaf)) { throw "ELF not found" }

$logs = Join-Path $EvidenceRoot "logs"
$reports = Join-Path $EvidenceRoot "reports"
New-Item -ItemType Directory -Path $logs, $reports -Force | Out-Null
$started = (Get-Date).ToUniversalTime().ToString("o")
$log = Join-Path $logs ("flash-{0}.log" -f $Purpose)
& $Programmer -c "port=SWD" "sn=$ProbeSerial" -d $Elf -v -rst *> $log
$exitCode = $LASTEXITCODE
$logText = Get-Content -LiteralPath $log -Raw
$report = [ordered]@{
    started_at_utc = $started
    ended_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    purpose = $Purpose
    programmer = $Programmer
    probe_serial = $ProbeSerial
    elf = $Elf
    elf_length = (Get-Item -LiteralPath $Elf).Length
    elf_sha256 = (Get-FileHash -LiteralPath $Elf -Algorithm SHA256).Hash.ToLowerInvariant()
    action = "download_verify_reset"
    exit_code = $exitCode
    download_verified = ($logText -match 'Download verified successfully')
    product_source_modified = $false
    log = $log
}
$reportPath = Join-Path $reports ("flash-{0}.json" -f $Purpose)
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 4
if ($exitCode -ne 0 -or -not $report.download_verified) { exit 1 }
