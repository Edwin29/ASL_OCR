param(
    [Parameter(Mandatory = $true)] [string] $EvidenceRoot
)

$ErrorActionPreference = "Stop"
$productRoot = "C:\ASL_OCR_INTEGRATION\hardware\stm32\kitel2026final"
$stagingRoot = Join-Path $EvidenceRoot "staging"
$backupRoot = Join-Path $EvidenceRoot "backup"
$reportRoot = Join-Path $EvidenceRoot "reports"
New-Item -ItemType Directory -Path $backupRoot, $reportRoot -Force | Out-Null

$files = @(
    [ordered]@{ Relative = "Core\Src\main.c"; Old = "c4bb35e208bf2bdcd4e773c4a40f5a5982ff0333e479340bcd9b6fa1c996371f"; New = "f0b93413f352be398dac62db6a64b2d17c19f1b8e14faf874371beddaf6ba1c1" },
    [ordered]@{ Relative = "Core\Src\stm32f4xx_it.c"; Old = "3681076251d67ff46ca8c70b200fc228fbebd08260fe84ed8e68e9647cf8b1b6"; New = "71030ed19863327bc4053916f16136e0b760bc77ca6efbba2f0f53d2dc3680a3" },
    [ordered]@{ Relative = "Core\Inc\main.h"; Old = "91a8f012d92f8c763905fb41edb1d281907d431dad9d3a95a77800afa69371ba"; New = "f802d2972e2ac9de4679d4914482ad468dd2098d383a91abb957083fa2e513a3" },
    [ordered]@{ Relative = "Core\Inc\stm32f4xx_it.h"; Old = "a8b16d0e7cf5defc41dc52c9cc1341ca4deba9789cc8e60ea6fb76a8503b5a6d"; New = "dd14fbf6d042467d063e09e8c3383b7d67655c84510178cd8de336f533916f7b" }
)

$started = (Get-Date).ToUniversalTime().ToString("o")
$applied = New-Object System.Collections.Generic.List[string]
$rolledBack = $false

foreach ($entry in $files) {
    $target = Join-Path $productRoot $entry.Relative
    $stage = Join-Path $stagingRoot $entry.Relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Target missing: $($entry.Relative)" }
    if (-not (Test-Path -LiteralPath $stage -PathType Leaf)) { throw "Staged file missing: $($entry.Relative)" }
    $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
    $stageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stage).Hash.ToLowerInvariant()
    if ($targetHash -ne $entry.Old) { throw "Expected old hash mismatch: $($entry.Relative)" }
    if ($stageHash -ne $entry.New) { throw "Candidate hash mismatch: $($entry.Relative)" }
}

foreach ($entry in $files) {
    $target = Join-Path $productRoot $entry.Relative
    $backup = Join-Path $backupRoot $entry.Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
    Copy-Item -LiteralPath $target -Destination $backup
}

try {
    foreach ($entry in $files) {
        $target = Join-Path $productRoot $entry.Relative
        $stage = Join-Path $stagingRoot $entry.Relative
        Copy-Item -LiteralPath $stage -Destination $target
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
        if ($actual -ne $entry.New) { throw "Post-copy hash mismatch: $($entry.Relative)" }
        $applied.Add($entry.Relative)
    }
}
catch {
    foreach ($entry in $files) {
        $target = Join-Path $productRoot $entry.Relative
        $backup = Join-Path $backupRoot $entry.Relative
        if (Test-Path -LiteralPath $backup -PathType Leaf) { Copy-Item -LiteralPath $backup -Destination $target -Force }
    }
    $rolledBack = $true
    throw
}
finally {
    $records = foreach ($entry in $files) {
        $target = Join-Path $productRoot $entry.Relative
        [ordered]@{
            relative_path = $entry.Relative
            expected_old_sha256 = $entry.Old
            candidate_sha256 = $entry.New
            actual_sha256 = if (Test-Path -LiteralPath $target) { (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant() } else { $null }
        }
    }
    $report = [ordered]@{
        started_at_utc = $started
        ended_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        product_root = $productRoot
        evidence_root = $EvidenceRoot
        expected_old_hashes_verified_before_write = $true
        backup_created = $true
        applied_files = @($applied)
        applied_file_count = $applied.Count
        rolled_back = $rolledBack
        files = @($records)
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $reportRoot "source-alignment.json") -Encoding UTF8
}

$report | ConvertTo-Json -Depth 5
