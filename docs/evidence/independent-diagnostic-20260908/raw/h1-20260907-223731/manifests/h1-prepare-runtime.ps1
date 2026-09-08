$ErrorActionPreference = 'Stop'

$runtimeRoot = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905'
$h0Config = Join-Path $runtimeRoot 'hardware-integration\h0-20260907-205411\config'
$runRoot = Join-Path $runtimeRoot 'hardware-integration\h1-20260907-223731'
$configRoot = Join-Path $runRoot 'config'
$secretRoot = Join-Path $configRoot 'secrets'

@(
    $configRoot,
    $secretRoot,
    (Join-Path $runRoot 'state\camera-console'),
    (Join-Path $runRoot 'logs'),
    (Join-Path $runRoot 'reports'),
    (Join-Path $runRoot 'captures'),
    (Join-Path $runRoot 'manifests')
) | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

Copy-Item -LiteralPath (Join-Path $h0Config 'device-connectivity.integration.toml') -Destination (Join-Path $configRoot 'device-connectivity.integration.toml') -Force
Copy-Item -LiteralPath (Join-Path $h0Config 'secrets\device-api-key.txt') -Destination (Join-Path $secretRoot 'device-api-key.txt') -Force
Copy-Item -LiteralPath (Join-Path $h0Config 'secrets\phone-camera-password.txt') -Destination (Join-Path $secretRoot 'phone-camera-password.txt') -Force

$identity = [ordered]@{
    run_root = $runRoot
    source_checkout = 'C:\ASL_OCR_INTEGRATION'
    python = 'C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe'
    config = (Join-Path $configRoot 'device-app.h1-camera-console.toml')
    state_root = (Join-Path $runRoot 'state\camera-console')
    controls = 'console'
    initial_mode = 'capture'
    device_id = 'laptop-device-001'
    credential_values_recorded = $false
    d_volume_dependency = 0
    product_source_modified = $false
}
$identity | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'manifests\h1-run-identity.json') -Encoding UTF8
$identity | ConvertTo-Json -Depth 4
