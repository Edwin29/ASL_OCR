param(
    [Parameter(Mandatory = $true)] [string] $SourceProject,
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Instrumenter,
    [Parameter(Mandatory = $true)] [string] $PythonExe,
    [Parameter(Mandatory = $true)] [string] $Builder
)

$ErrorActionPreference = "Stop"
$expectedRoot = "C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\"
if (-not $RunRoot.StartsWith($expectedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "RunRoot is outside the approved C: integration runtime"
}
if (Test-Path -LiteralPath $RunRoot) {
    throw "RunRoot already exists"
}

$projectCopy = Join-Path $RunRoot "firmware-build\source\kitel2026final"
$workspace = Join-Path $RunRoot "firmware-build\workspace"
$logs = Join-Path $RunRoot "logs"
$manifests = Join-Path $RunRoot "manifests"
$reports = Join-Path $RunRoot "reports"
New-Item -ItemType Directory -Path (Split-Path $projectCopy), $workspace, $logs, $manifests, $reports -Force | Out-Null
Copy-Item -LiteralPath $SourceProject -Destination $projectCopy -Recurse

$main = Join-Path $projectCopy "Core\Src\main.c"
$before = (Get-FileHash -LiteralPath $main -Algorithm SHA256).Hash.ToLowerInvariant()
& $PythonExe $Instrumenter $main
if ($LASTEXITCODE -ne 0) { throw "instrumenter failed with exit code $LASTEXITCODE" }
$after = (Get-FileHash -LiteralPath $main -Algorithm SHA256).Hash.ToLowerInvariant()
if ($before -eq $after) { throw "instrumenter made no change" }

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
    diagnostic_only = $true
    product_source_modified = $false
    source_project = $SourceProject
    project_copy = $projectCopy
    workspace = $workspace
    instrumenter = $Instrumenter
    source_main_sha256_before = $before
    source_main_sha256_after = $after
    builder = $Builder
    build_log = $buildLog
    build_exit_code = $buildExit
    build_has_error_marker = ($logText -match '(?im)^.*\berror[: ]')
    artifact = $artifact
}
$manifestPath = Join-Path $manifests "rx-diagnostic-build.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$manifest | ConvertTo-Json -Depth 5
if ($buildExit -ne 0 -or $null -eq $artifact) { exit 1 }
