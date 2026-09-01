[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$tailscale = "C:\Program Files\Tailscale\tailscale.exe"
if (-not (Test-Path -LiteralPath $tailscale -PathType Leaf)) {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($null -eq $command) { throw "Tailscale is not installed." }
    $tailscale = $command.Source
}

& $tailscale serve reset
if ($LASTEXITCODE -ne 0) { throw "Could not reset Tailscale Serve. Try running this script as Administrator." }
Write-Host "[E0-B.1] Tailscale Serve configuration was removed."
