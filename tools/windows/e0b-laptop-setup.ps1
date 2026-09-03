[CmdletBinding()]
param(
    [string]$ConfigRoot = "D:\ASL_OCR_E0B",
    [string]$ServerOrigin,
    [string]$DeviceId = "laptop-device-001",
    [string]$ComPort = "COM5",
    [int]$CameraIndex = 0,
    [int]$CameraWidth = 3840,
    [int]$CameraHeight = 2160,
    [double]$CameraFps = 30.0,
    [ValidateSet("hardware", "webcam")]
    [string]$TestProfile = "hardware",
    [string]$ReplayVideo,
    [string]$ModelBundle,
    [string]$ApiKeySource,
    [string]$VenvRoot,
    [switch]$SkipInstall,
    [switch]$SkipHealthCheck,
    [switch]$SkipPreflight,
    [switch]$DisableCameraPreview,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Set-TomlQuoted([string]$Path, [string]$Key, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '["\r\n]') {
        throw "Invalid TOML value for $Key"
    }
    $content = [System.IO.File]::ReadAllText($Path)
    $pattern = '(?m)^' + [regex]::Escape($Key) + '\s*=\s*"[^"]*"\s*$'
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "TOML key not found: $Key in $Path"
    }
    $replacement = $Key + ' = "' + $Value + '"'
    Write-Utf8NoBom $Path ([regex]::Replace($content, $pattern, $replacement))
}

function Set-TomlNumber([string]$Path, [string]$Key, [string]$Value) {
    $content = [System.IO.File]::ReadAllText($Path)
    $pattern = '(?m)^' + [regex]::Escape($Key) + '\s*=\s*[-+0-9.]+\s*$'
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "TOML key not found: $Key in $Path"
    }
    Write-Utf8NoBom $Path ([regex]::Replace($content, $pattern, ($Key + ' = ' + $Value)))
}

function Set-TomlBoolean([string]$Path, [string]$Key, [bool]$Value) {
    $content = [System.IO.File]::ReadAllText($Path)
    $pattern = '(?m)^' + [regex]::Escape($Key) + '\s*=\s*(true|false)\s*$'
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "TOML key not found: $Key in $Path"
    }
    $replacement = $Key + ' = ' + $(if ($Value) { 'true' } else { 'false' })
    Write-Utf8NoBom $Path ([regex]::Replace($content, $pattern, $replacement))
}

function Resolve-Python311 {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        & $launcher.Source -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            return @($launcher.Source, "-3.11")
        }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            return @($python.Source)
        }
    }
    throw "Python 3.11 is required. Install it from python.org and select Add python.exe to PATH."
}

function Read-Default([string]$Prompt, [string]$Default) {
    $value = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$configRootPath = [System.IO.Path]::GetFullPath($ConfigRoot)
if ([string]::IsNullOrWhiteSpace($VenvRoot)) {
    $venvRoot = Join-Path $repoRoot ".venv-e0b"
} else {
    $venvRoot = [System.IO.Path]::GetFullPath($VenvRoot)
}
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$connectivityConfig = Join-Path $configRootPath "device-connectivity.e0b.remote.toml"
$secretPath = Join-Path $configRootPath "secrets\device-api-key.txt"
$replayReportPath = Join-Path $configRootPath "reports\e0b-replay-input.json"
$replayMode = -not [string]::IsNullOrWhiteSpace($ReplayVideo)
$requiresStm = -not $replayMode -and $TestProfile -eq "hardware"
$profileName = if ($replayMode) { "replay" } else { $TestProfile }
$appConfig = Join-Path $configRootPath "device-app.e0b.$profileName.toml"
$compatibilityAppConfig = Join-Path $configRootPath "device-app.e0b.toml"
$reportPath = Join-Path $configRootPath "reports\e0b-preflight-$profileName.json"

Write-Host "[E0-B] Repository: $repoRoot"
Write-Host "[E0-B] Config root: $configRootPath"
Write-Host "[E0-B] Test profile: $profileName"

if (-not $NonInteractive) {
    if ([string]::IsNullOrWhiteSpace($ServerOrigin)) {
        $ServerOrigin = (Read-Host "Private HTTPS Server origin (for example https://desktop.example-tailnet.ts.net)").Trim()
    }
    $DeviceId = Read-Default "Device ID" $DeviceId
    if (-not $replayMode) {
        if ($requiresStm) {
            $ComPort = Read-Default "STM Bluetooth COM port" $ComPort
        }
        $CameraIndex = [int](Read-Default "Camera index" ([string]$CameraIndex))
        $CameraWidth = [int](Read-Default "Camera width" ([string]$CameraWidth))
        $CameraHeight = [int](Read-Default "Camera height" ([string]$CameraHeight))
        $CameraFps = [double](Read-Default "Camera FPS" ([string]$CameraFps))
    }
    if ([string]::IsNullOrWhiteSpace($ModelBundle)) {
        $ModelBundle = (Read-Host "Model bundle directory containing uvdoc/ and paddle/ (required)").Trim()
    }
}

$originUri = $null
if (-not [Uri]::TryCreate($ServerOrigin, [UriKind]::Absolute, [ref]$originUri) -or
    $originUri.Scheme -ne "https" -or
    [string]::IsNullOrWhiteSpace($originUri.Host) -or
    $originUri.AbsolutePath -ne "/" -or
    $originUri.Query -or
    $originUri.Fragment -or
    $originUri.Host -in @("localhost", "127.0.0.1", "::1")) {
    throw "ServerOrigin must be a non-loopback HTTPS origin without a path, query, or fragment."
}
if ($DeviceId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') { throw "DeviceId is invalid." }
if ($requiresStm) {
    if ($ComPort -notmatch '^COM[0-9]+$') { throw "ComPort must look like COM5." }
}
if (-not $replayMode) {
    if ($CameraIndex -lt 0 -or $CameraWidth -lt 320 -or $CameraHeight -lt 240 -or $CameraFps -le 0 -or $CameraFps -gt 120) {
        throw "Camera settings are outside the supported setup range."
    }
}

if (-not $SkipInstall) {
    $bootstrap = @(Resolve-Python311)
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "[E0-B] Creating Python 3.11 virtual environment..."
        if ($bootstrap.Count -eq 2) {
            & $bootstrap[0] $bootstrap[1] -m venv $venvRoot
        } else {
            & $bootstrap[0] -m venv $venvRoot
        }
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment." }
    }
    Write-Host "[E0-B] Installing pinned Laptop runtime dependencies..."
    & $venvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed." }
    & $venvPython -m pip install -r (Join-Path $repoRoot "device-runtime\requirements-e0b-laptop.txt")
    if ($LASTEXITCODE -ne 0) { throw "Laptop runtime dependency install failed." }
    & $venvPython -m pip install -e ((Join-Path $repoRoot "document-parser") + "[remote-ingest]") -e (Join-Path $repoRoot "book-scanner") -e ((Join-Path $repoRoot "device-runtime") + "[laptop,audio]")
    if ($LASTEXITCODE -ne 0) { throw "Local package install failed." }
} elseif (-not (Test-Path -LiteralPath $venvPython)) {
    throw "SkipInstall was requested but $venvPython does not exist."
}

foreach ($directory in @(
    $configRootPath,
    (Join-Path $configRootPath "secrets"),
    (Join-Path $configRootPath "reports"),
    (Join-Path $configRootPath "inputs"),
    (Join-Path $configRootPath "state\artifacts\staging"),
    (Join-Path $configRootPath "state\artifacts\ready"),
    (Join-Path $configRootPath "models")
)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$appTemplate = if ($replayMode) {
    "device-app.e0b.replay.example.toml"
} elseif ($TestProfile -eq "hardware") {
    "device-app.e0b.laptop.example.toml"
} else {
    "device-app.e0b.webcam.example.toml"
}
Copy-Item -LiteralPath (Join-Path $repoRoot "device-runtime\$appTemplate") -Destination $appConfig -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "device-runtime\device-connectivity.e0b.remote.example.toml") -Destination $connectivityConfig -Force

Set-TomlQuoted $connectivityConfig "server_base_url" $originUri.GetLeftPart([UriPartial]::Authority)
Set-TomlQuoted $connectivityConfig "device_id" $DeviceId
if ($requiresStm) {
    Set-TomlQuoted $appConfig "port" $ComPort
}
if (-not $replayMode) {
    Set-TomlNumber $appConfig "camera_index" ([string]$CameraIndex)
    Set-TomlNumber $appConfig "camera_width" ([string]$CameraWidth)
    Set-TomlNumber $appConfig "camera_height" ([string]$CameraHeight)
    Set-TomlNumber $appConfig "camera_fps" $CameraFps.ToString([Globalization.CultureInfo]::InvariantCulture)
    Set-TomlBoolean $appConfig "operator_preview_enabled" (-not $DisableCameraPreview)
}

if (-not [string]::IsNullOrWhiteSpace($ApiKeySource)) {
    $resolvedKeySource = (Resolve-Path -LiteralPath $ApiKeySource).Path
    $apiKey = [System.IO.File]::ReadAllText($resolvedKeySource).Trim()
    if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -gt 4096 -or $apiKey -match '[\r\n]') {
        throw "ApiKeySource contains an invalid API key."
    }
    Write-Utf8NoBom $secretPath $apiKey
} elseif (-not (Test-Path -LiteralPath $secretPath)) {
    if ($NonInteractive) { throw "ApiKeySource is required in NonInteractive mode." }
    $secureKey = Read-Host "Shared API key (same value as Desktop Server)" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -gt 4096 -or $apiKey -match '[\r\n]') {
        throw "The API key is invalid."
    }
    Write-Utf8NoBom $secretPath $apiKey
}

if ([string]::IsNullOrWhiteSpace($ModelBundle)) {
    throw "ModelBundle is required. See the Laptop runbook for its directory layout."
}
$modelBundlePath = (Resolve-Path -LiteralPath $ModelBundle).Path
$requiredModelPaths = @(
    "uvdoc\runtime\model.py",
    "uvdoc\checkpoint.pth",
    "paddle\page-number\inference.json",
    "paddle\page-number\inference.pdiparams",
    "paddle\page-number\inference.yml",
    "paddle\page-number-manifest.json"
)
foreach ($relativePath in $requiredModelPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $modelBundlePath $relativePath))) {
        throw "Model bundle is incomplete: $relativePath"
    }
}
$manifestPath = Join-Path $modelBundlePath "paddle\page-number-manifest.json"
$modelRoot = (Resolve-Path -LiteralPath (Join-Path $modelBundlePath "paddle\page-number")).Path
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.runtime_download_allowed -ne $false -or $null -eq $manifest.files) {
    throw "M1 model manifest contract is invalid."
}
foreach ($asset in $manifest.files.PSObject.Properties) {
    $relativeAsset = [string]$asset.Name
    $expectedHash = ([string]$asset.Value).ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($relativeAsset) -or
        [System.IO.Path]::IsPathRooted($relativeAsset) -or
        $relativeAsset -match '(^|[\\/])\.\.([\\/]|$)' -or
        $expectedHash -notmatch '^[0-9a-f]{64}$') {
        throw "M1 model manifest contains an unsafe asset entry."
    }
    $assetPath = [System.IO.Path]::GetFullPath((Join-Path $modelRoot $relativeAsset))
    if (-not $assetPath.StartsWith($modelRoot + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
        throw "M1 model asset is missing: $relativeAsset"
    }
    $actualHash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "M1 model asset hash mismatch: $relativeAsset"
    }
}
Copy-Item -Path (Join-Path $modelBundlePath "*") -Destination (Join-Path $configRootPath "models") -Recurse -Force

# Preserve the historical default filename for replay scripts and existing
# operator notes while retaining independently runnable named profiles.
Copy-Item -LiteralPath $appConfig -Destination $compatibilityAppConfig -Force

if ($replayMode) {
    $replaySource = (Resolve-Path -LiteralPath $ReplayVideo).Path
    if (-not (Test-Path -LiteralPath $replaySource -PathType Leaf)) {
        throw "ReplayVideo must name a video file."
    }
    $replayDestination = Join-Path $configRootPath "inputs\scanner-replay.mp4"
    if (-not [string]::Equals($replaySource, $replayDestination, [StringComparison]::OrdinalIgnoreCase)) {
        Copy-Item -LiteralPath $replaySource -Destination $replayDestination -Force
    }
    Write-Host "[E0-B.1] Validating the prepared replay video..."
    & $venvPython (Join-Path $scriptDir "e0b_replay_check.py") $replayDestination $replayReportPath
    if ($LASTEXITCODE -ne 0) { throw "Replay video validation failed." }
}

Write-Host "[E0-B] Configuration and model bundle are ready."
if (-not $SkipHealthCheck) {
    & $venvPython (Join-Path $scriptDir "e0b_health_check.py") $originUri.GetLeftPart([UriPartial]::Authority)
    if ($LASTEXITCODE -ne 0) { throw "Remote Server health check failed." }
}

if ($replayMode -and -not $SkipPreflight) {
    Write-Host "[E0-B.1] Hardware preflight is not applicable to replay mode and will be skipped."
} elseif (-not $SkipPreflight) {
    if ($requiresStm) {
        Write-Host "[E0-B] Running hardware preflight. Camera, STM COM, authenticated Piper WAV, and Laptop audio output will be exercised."
    } else {
        Write-Host "[E0-B] Running webcam preflight. Camera, server, authenticated Piper WAV, and Laptop audio output will be exercised; STM is not opened."
    }
    & $venvPython -m asl_device --config $appConfig --preflight --report $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Laptop preflight failed. See $reportPath" }
}

Write-Host "[E0-B] App config: $appConfig"
if ($replayMode) {
    Write-Host "[E0-B.1] Replay report: $replayReportPath"
    Write-Host "[E0-B.1] Replay run: tools\windows\e0b-replay-run.bat $configRootPath"
} else {
    Write-Host "[E0-B] Preflight: tools\windows\e0b-laptop-preflight.bat $configRootPath $TestProfile"
    Write-Host "[E0-B] Full run: tools\windows\e0b-laptop-run.bat $configRootPath $TestProfile"
}
