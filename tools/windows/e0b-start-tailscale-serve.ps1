[CmdletBinding()]
param(
    [int]$LocalPort = 8421
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-TailscaleExe {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $installed = "C:\Program Files\Tailscale\tailscale.exe"
    if (Test-Path -LiteralPath $installed -PathType Leaf) { return $installed }
    throw "Tailscale is not installed. Install it on Desktop and sign in before running this script."
}

if ($LocalPort -lt 1 -or $LocalPort -gt 65535) { throw "LocalPort must be between 1 and 65535." }

$tailscale = Resolve-TailscaleExe
$localOrigin = "http://127.0.0.1:$LocalPort"
$localHealth = Invoke-RestMethod -Uri "$localOrigin/api/v1/health" -TimeoutSec 10
if ($localHealth.status -ne "ok" -or [string]::IsNullOrWhiteSpace([string]$localHealth.server_instance_id)) {
    throw "The local E0-B Server health response is not ready."
}

$statusText = & $tailscale status --json
if ($LASTEXITCODE -ne 0) { throw "Could not read Tailscale status. Try running this script as Administrator." }
$status = $statusText | ConvertFrom-Json
if ($status.BackendState -ne "Running" -or $status.Self.Online -ne $true) {
    throw "Tailscale must be connected before Serve can start."
}
$dnsName = ([string]$status.Self.DNSName).Trim().TrimEnd(".")
if ([string]::IsNullOrWhiteSpace($dnsName) -or $dnsName -notmatch '\.ts\.net$') {
    throw "Tailscale MagicDNS name is unavailable. Enable HTTPS/MagicDNS for this tailnet."
}

& $tailscale serve --bg --yes $LocalPort
if ($LASTEXITCODE -ne 0) { throw "Tailscale Serve configuration failed." }

$serveStatus = & $tailscale serve status --json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($serveStatus -join ""))) {
    throw "Tailscale Serve did not return an active configuration."
}

$origin = "https://$dnsName"
$remoteHealth = Invoke-RestMethod -Uri "$origin/api/v1/health" -TimeoutSec 15
if ($remoteHealth.status -ne "ok" -or $remoteHealth.server_instance_id -ne $localHealth.server_instance_id) {
    throw "Tailscale Serve health did not resolve to the local E0-B Server instance."
}

Write-Host "[E0-B.1] Tailscale Serve is ready for devices signed into the same tailnet."
Write-Host "[E0-B.1] ORIGIN=$origin"
Write-Host "[E0-B.1] Health: $origin/api/v1/health"
