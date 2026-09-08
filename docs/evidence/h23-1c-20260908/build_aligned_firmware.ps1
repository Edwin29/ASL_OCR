param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Builder
)

$ErrorActionPreference = "Stop"
$approvedRoot = "C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\"
$sourceProject = "C:\ASL_OCR_INTEGRATION\hardware\stm32\kitel2026final"
if (-not $RunRoot.StartsWith($approvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "RunRoot is outside the approved C: integration evidence runtime"
}
if (Test-Path -LiteralPath $RunRoot) { throw "RunRoot already exists" }

$expected = [ordered]@{
    "Core\Src\main.c" = "f0b93413f352be398dac62db6a64b2d17c19f1b8e14faf874371beddaf6ba1c1"
    "Core\Src\stm32f4xx_it.c" = "71030ed19863327bc4053916f16136e0b760bc77ca6efbba2f0f53d2dc3680a3"
    "Core\Inc\main.h" = "f802d2972e2ac9de4679d4914482ad468dd2098d383a91abb957083fa2e513a3"
    "Core\Inc\stm32f4xx_it.h" = "dd14fbf6d042467d063e09e8c3383b7d67655c84510178cd8de336f533916f7b"
}

$sourceFiles = @()
foreach ($relative in $expected.Keys) {
    $path = Join-Path $sourceProject $relative
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $expected[$relative]) { throw "Aligned source hash mismatch: $relative" }
    $sourceFiles += [ordered]@{ relative_path = $relative; sha256 = $actual }
}

$projectCopy = Join-Path $RunRoot "firmware-build\source\kitel2026final"
$workspace = Join-Path $RunRoot "firmware-build\workspace"
$logs = Join-Path $RunRoot "logs"
$manifests = Join-Path $RunRoot "manifests"
New-Item -ItemType Directory -Path (Split-Path $projectCopy), $workspace, $logs, $manifests -Force | Out-Null
Copy-Item -LiteralPath $sourceProject -Destination $projectCopy -Recurse

$buildLog = Join-Path $logs "stm32-cubeide-clean-build.log"
& $Builder -data $workspace -import $projectCopy -cleanBuild "kitel2026final/Debug" *> $buildLog
$buildExit = $LASTEXITCODE
$elf = Join-Path $projectCopy "Debug\kitel2026final.elf"
$artifact = $null
if (Test-Path -LiteralPath $elf -PathType Leaf) {
    $artifact = [ordered]@{
        path = $elf
        length = (Get-Item -LiteralPath $elf).Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLowerInvariant()
    }
}
$logText = if (Test-Path -LiteralPath $buildLog) { Get-Content -LiteralPath $buildLog -Raw } else { "" }
$manifest = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    identity = "authoritative integration source after USART1 RX alignment"
    product_source_modified_on_laptop = $true
    source_project = $sourceProject
    project_copy = $projectCopy
    source_files = $sourceFiles
    builder = $Builder
    build_log = $buildLog
    build_exit_code = $buildExit
    build_has_error_marker = ($logText -match '(?im)^.*\berror[: ]')
    artifact = $artifact
  }
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $manifests "aligned-firmware-build.json") -Encoding UTF8
$manifest | ConvertTo-Json -Depth 6
if ($buildExit -ne 0 -or $null -eq $artifact -or $manifest.build_has_error_marker) { exit 1 }
