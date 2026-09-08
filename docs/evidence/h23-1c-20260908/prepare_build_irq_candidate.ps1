param(
    [Parameter(Mandatory = $true)] [string] $SourceProject,
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $StagingRoot,
    [Parameter(Mandatory = $true)] [string] $Builder
)

$ErrorActionPreference = "Stop"
$approvedRoot = "C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\"
if (-not $RunRoot.StartsWith($approvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "RunRoot is outside the approved C: integration evidence runtime"
}
if (Test-Path -LiteralPath $RunRoot) { throw "RunRoot already exists" }

$relativeFiles = @(
    "Core\Src\main.c",
    "Core\Src\stm32f4xx_it.c",
    "Core\Inc\main.h",
    "Core\Inc\stm32f4xx_it.h"
)
foreach ($relative in $relativeFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $StagingRoot $relative) -PathType Leaf)) {
        throw "Missing staged file: $relative"
    }
}

$projectCopy = Join-Path $RunRoot "firmware-build\source\kitel2026final"
$workspace = Join-Path $RunRoot "firmware-build\workspace"
$logs = Join-Path $RunRoot "logs"
$manifests = Join-Path $RunRoot "manifests"
$reports = Join-Path $RunRoot "reports"
New-Item -ItemType Directory -Path (Split-Path $projectCopy), $workspace, $logs, $manifests, $reports -Force | Out-Null
Copy-Item -LiteralPath $SourceProject -Destination $projectCopy -Recurse

$files = @()
foreach ($relative in $relativeFiles) {
    $sourcePath = Join-Path $SourceProject $relative
    $stagedPath = Join-Path $StagingRoot $relative
    $targetPath = Join-Path $projectCopy $relative
    $before = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $candidate = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $stagedPath -Destination $targetPath
    $after = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($candidate -ne $after) { throw "Candidate copy hash mismatch: $relative" }
    $files += [ordered]@{
        relative_path = $relative
        source_sha256 = $before
        candidate_sha256 = $candidate
        changed = ($before -ne $candidate)
    }
}

$buildLog = Join-Path $logs "stm32-cubeide-clean-build.log"
& $Builder -data $workspace -import $projectCopy -cleanBuild "kitel2026final/Debug" *> $buildLog
$buildExit = $LASTEXITCODE
$elf = Join-Path $projectCopy "Debug\kitel2026final.elf"
$artifact = $null
if (Test-Path -LiteralPath $elf) {
    $item = Get-Item -LiteralPath $elf
    $artifact = [ordered]@{
        path = $item.FullName
        length = $item.Length
        sha256 = (Get-FileHash -LiteralPath $elf -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$logText = if (Test-Path -LiteralPath $buildLog) { Get-Content -LiteralPath $buildLog -Raw } else { "" }
$manifest = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    candidate = "USART1 interrupt ring"
    product_source_modified_on_laptop = $false
    source_project = $SourceProject
    staging_root = $StagingRoot
    project_copy = $projectCopy
    workspace = $workspace
    changed_files = $files
    changed_file_count = @($files | Where-Object { $_.changed }).Count
    builder = $Builder
    build_log = $buildLog
    build_exit_code = $buildExit
    build_has_error_marker = ($logText -match '(?im)^.*\berror[: ]')
    artifact = $artifact
}
$manifestPath = Join-Path $manifests "irq-candidate-build.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$manifest | ConvertTo-Json -Depth 6
if ($buildExit -ne 0 -or $null -eq $artifact -or $manifest.changed_file_count -ne 4) { exit 1 }
