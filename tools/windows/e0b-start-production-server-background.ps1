param(
    [string]$LogDirectory = 'D:\device-config\state\e0b-production\logs'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcher = Join-Path $PSScriptRoot 'e0b-start-production-server.bat'
if (Get-NetTCPConnection -LocalPort 8421 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8421 is already in use. No additional server was started.'
}
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$stdoutPath = Join-Path $LogDirectory "server-$runId.out.log"
$stderrPath = Join-Path $LogDirectory "server-$runId.err.log"
# On Windows, Start-Process launches independently of this PowerShell session.
# Redirect both streams so no terminal handle is needed to keep the server alive.
$process = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
    -ArgumentList @('/d', '/c', "call `"$launcher`"") `
    -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
[pscustomobject]@{
    launcher_pid = $process.Id
    stdout = $stdoutPath
    stderr = $stderrPath
    health_url = 'http://127.0.0.1:8421/api/v1/health'
    note = 'Process launched; verify health separately. No auto-start or restart policy is installed.'
} | ConvertTo-Json
