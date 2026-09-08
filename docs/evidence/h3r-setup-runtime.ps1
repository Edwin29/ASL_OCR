$ErrorActionPreference = 'Stop'
$sourceRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3-20260908-001800'
$h2Root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639'
$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'

New-Item -ItemType Directory -Force -Path @(
    (Join-Path $root 'config'),
    (Join-Path $root 'state\console-stm'),
    (Join-Path $root 'logs'),
    (Join-Path $root 'reports'),
    (Join-Path $root 'manifests')
) | Out-Null

$oldApp = Join-Path $sourceRoot 'config\device-app.stm-reading.toml'
$appText = [IO.File]::ReadAllText($oldApp)
$appText = $appText.Replace(
    'h3-20260908-001800/state/stm-reading',
    'h3r-20260908-reading-output/state/console-stm'
)
$appText = [regex]::Replace(
    $appText,
    '(?m)^camera_snapshot_password_file\s*=.*$',
    'camera_snapshot_password_file = "C:/ASL_OCR_INTEGRATION_RUNTIME/demo-20260905/hardware-integration/h3-20260908-001800/config/secrets/phone-camera-password.txt"'
)
$appPath = Join-Path $root 'config\device-app.h3r-console-stm.toml'
[IO.File]::WriteAllText($appPath, $appText, [Text.UTF8Encoding]::new($false))

$connText = [IO.File]::ReadAllText(
    (Join-Path $sourceRoot 'config\device-connectivity.integration.toml')
)
$connText = [regex]::Replace(
    $connText,
    '(?m)^api_key_file\s*=.*$',
    'api_key_file = "C:/ASL_OCR_INTEGRATION_RUNTIME/demo-20260905/hardware-integration/h3-20260908-001800/config/secrets/device-api-key.txt"'
)
$connPath = Join-Path $root 'config\device-connectivity.integration.toml'
[IO.File]::WriteAllText($connPath, $connText, [Text.UTF8Encoding]::new($false))

$harness = [IO.File]::ReadAllText(
    (Join-Path $h2Root 'manifests\h2-console-stm-harness.py')
)
$harness = $harness.Replace('h2-20260907-234639', 'h3r-20260908-reading-output')
$harness = $harness.Replace('device-app.h2-console-stm.toml', 'device-app.h3r-console-stm.toml')
$harness = $harness.Replace('h2-events.jsonl', 'h3r-events.jsonl')
$harness = $harness.Replace('"type":"h2_start"', '"type":"h3r_start"')
$harness = $harness.Replace('"type":"h2_stop"', '"type":"h3r_stop"')
$harnessPath = Join-Path $root 'manifests\h3r-console-stm-harness.py'
[IO.File]::WriteAllText($harnessPath, $harness, [Text.UTF8Encoding]::new($false))

$com5 = [IO.File]::ReadAllText((Join-Path $h2Root 'manifests\com5-trace.py'))
$com5 = $com5.Replace('h2-20260907-234639', 'h3r-20260908-reading-output')
$com5Path = Join-Path $root 'manifests\com5-trace.py'
[IO.File]::WriteAllText($com5Path, $com5, [Text.UTF8Encoding]::new($false))

$runtime = @'
$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:\ASL_OCR_INTEGRATION'
$env:PYTHONUTF8='1'
& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\manifests\h3r-console-stm-harness.py'
'@
[IO.File]::WriteAllText(
    (Join-Path $root 'manifests\h3r-runtime.ps1'),
    $runtime,
    [Text.UTF8Encoding]::new($false)
)

& 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe' -c @"
from asl_device.app_config import DeviceAppConfig
c=DeviceAppConfig.from_toml(r'$appPath')
print(c.connectivity.device_id, c.stm_serial.port, c.viewport_size)
"@

$dReferences = Get-ChildItem -LiteralPath $root -File -Recurse |
    Select-String -Pattern 'D:' -SimpleMatch
if ($dReferences) {
    throw 'D dependency found'
}

$identity = [ordered]@{
    run_root = $root
    source = 'C:\ASL_OCR_INTEGRATION'
    python = 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe'
    controls = 'console'
    presenter = 'stm_serial'
    device_id = 'laptop-device-001'
    stm_port = 'COM9'
    debug_port = 'COM5'
    initial_mode = 'reading'
    credential_reference_source = 'existing H3 C: runtime'
    product_source_modified = $false
    d_volume_dependency = 0
}
[IO.File]::WriteAllText(
    (Join-Path $root 'manifests\h3r-run-identity.json'),
    ($identity | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)

Get-FileHash -Algorithm SHA256 -LiteralPath @(
    $appPath,
    $connPath,
    $harnessPath,
    (Join-Path $root 'manifests\h3r-run-identity.json')
) | Select-Object Path, Hash
