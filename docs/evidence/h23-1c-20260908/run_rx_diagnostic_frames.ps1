param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Programmer,
    [string] $ProbeSerial = "0670FF485775495067203341",
    [int] $TriggerWaitSeconds = 600,
    [switch] $SkipReset
)

$ErrorActionPreference = "Stop"
$logs = Join-Path $RunRoot "logs"
$reports = Join-Path $RunRoot "reports"
$controlRoot = Join-Path $RunRoot "control"
New-Item -ItemType Directory -Path $logs, $reports, $controlRoot -Force | Out-Null

$eventPath = Join-Path $logs "rx-diagnostic-serial.jsonl"
$debugPath = Join-Path $logs "rx-diagnostic-com5.txt"
$resetPath = Join-Path $logs "rx-diagnostic-reset.log"
$readyPath = Join-Path $controlRoot "ready-for-trigger"
$triggerPath = Join-Path $controlRoot "trigger"
$donePath = Join-Path $controlRoot "done"
$resultPath = Join-Path $reports "rx-diagnostic-result.json"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$eventWriter = New-Object System.IO.StreamWriter($eventPath, $false, $utf8)
$eventWriter.AutoFlush = $true
$debugWriter = New-Object System.IO.StreamWriter($debugPath, $false, $utf8)
$debugWriter.AutoFlush = $true

function Write-SerialEvent {
    param([string] $Direction, [string] $Port, [byte[]] $Bytes, [string] $Role)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
    $eventWriter.WriteLine((([ordered]@{
        at_utc = (Get-Date).ToUniversalTime().ToString("o")
        direction = $Direction
        port = $Port
        role = $Role
        length = $Bytes.Length
        sha256 = $digest
        hex = [BitConverter]::ToString($Bytes).Replace("-", "").ToLowerInvariant()
        ascii = [Text.Encoding]::ASCII.GetString($Bytes)
    }) | ConvertTo-Json -Compress))
}

# One changing pattern followed by clear. Both are sent at production byte rate.
$frames = @(
    "FRAME,0,18,0,0,120,63,0,63,0,63,0,63,0,63,0`n",
    "FRAME,0,19,0,0,121,0,0,0,0,0,0,0,0,0,0`n"
)

$debugPort = New-Object System.IO.Ports.SerialPort("COM5", 115200, "None", 8, "One")
$hostPort = New-Object System.IO.Ports.SerialPort("COM9", 9600, "None", 8, "One")
$debugPort.ReadTimeout = 50
$hostPort.ReadTimeout = 50
$hostPort.WriteTimeout = 500
$hostBuffer = ""
$debugBuffer = ""
$hello3 = 0
$navPackets = New-Object System.Collections.Generic.List[string]
$framesSent = 0
$triggered = $false
$stopReason = "timeout_waiting_for_trigger"
$errorText = $null

function Pump-Ports {
    if ($debugPort.BytesToRead -gt 0) {
        $buffer = New-Object byte[] ([Math]::Min(4096, $debugPort.BytesToRead))
        $count = $debugPort.Read($buffer, 0, $buffer.Length)
        if ($count -gt 0) {
            [byte[]]$bytes = $buffer[0..($count - 1)]
            Write-SerialEvent "rx" "COM5" $bytes "debug"
            $text = [Text.Encoding]::ASCII.GetString($bytes)
            $script:debugBuffer += $text
            $debugWriter.Write($text)
        }
    }
    if ($hostPort.BytesToRead -gt 0) {
        $buffer = New-Object byte[] ([Math]::Min(4096, $hostPort.BytesToRead))
        $count = $hostPort.Read($buffer, 0, $buffer.Length)
        if ($count -gt 0) {
            [byte[]]$bytes = $buffer[0..($count - 1)]
            Write-SerialEvent "rx" "COM9" $bytes "firmware_to_host"
            $script:hostBuffer += [Text.Encoding]::ASCII.GetString($bytes)
            while ($script:hostBuffer.Contains("`n")) {
                $newline = $script:hostBuffer.IndexOf("`n")
                $line = $script:hostBuffer.Substring(0, $newline).TrimEnd("`r")
                $script:hostBuffer = $script:hostBuffer.Substring($newline + 1)
                if ($line -eq "HELLO,3") {
                    $script:hello3++
                    [byte[]]$payload = [Text.Encoding]::ASCII.GetBytes("ACK,HELLO,3`n")
                    $hostPort.Write($payload, 0, $payload.Length)
                    Write-SerialEvent "tx" "COM9" $payload "handshake_ack"
                }
                elseif ($line -match '^NAV,([UDLRNPCV]),([ASRL]),([0-9]+)$') {
                    $script:navPackets.Add($line)
                    [byte[]]$payload = [Text.Encoding]::ASCII.GetBytes("ACK,$($Matches[3])`n")
                    $hostPort.Write($payload, 0, $payload.Length)
                    Write-SerialEvent "tx" "COM9" $payload "nav_ack"
                }
            }
        }
    }
}

try {
    $debugPort.Open()
    $hostPort.Open()
    if ($SkipReset) {
        [IO.File]::WriteAllText($resetPath, "reset skipped; using the verified reset performed by diagnostic flash", $utf8)
    }
    else {
        & $Programmer -c "port=SWD" "sn=$ProbeSerial" -rst *> $resetPath
        if ($LASTEXITCODE -ne 0) { throw "STM32 reset failed with exit code $LASTEXITCODE" }
    }
    $handshakeDeadline = [DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $handshakeDeadline) {
        Pump-Ports
        if ($hello3 -ge 1 -and $navPackets.Count -ge 1 -and $debugBuffer.Contains("BT: HOST CONNECTED (V3 EDGES)")) { break }
        Start-Sleep -Milliseconds 10
    }
    if (-not ($hello3 -ge 1 -and $navPackets.Count -ge 1)) { throw "V3 handshake/initial mode did not complete" }

    [IO.File]::WriteAllText($readyPath, (Get-Date).ToUniversalTime().ToString("o"), $utf8)
    $triggerDeadline = [DateTime]::UtcNow.AddSeconds($TriggerWaitSeconds)
    while ([DateTime]::UtcNow -lt $triggerDeadline -and -not (Test-Path -LiteralPath $triggerPath)) {
        Pump-Ports
        Start-Sleep -Milliseconds 10
    }
    if (-not (Test-Path -LiteralPath $triggerPath)) { throw "trigger timeout" }
    $triggered = $true

    foreach ($frame in $frames) {
        [byte[]]$payload = [Text.Encoding]::ASCII.GetBytes($frame)
        $hostPort.Write($payload, 0, $payload.Length)
        Write-SerialEvent "tx" "COM9" $payload "frame"
        $framesSent++
        $until = [DateTime]::UtcNow.AddSeconds(4)
        while ([DateTime]::UtcNow -lt $until) {
            Pump-Ports
            Start-Sleep -Milliseconds 10
        }
    }
    $until = [DateTime]::UtcNow.AddSeconds(5)
    while ([DateTime]::UtcNow -lt $until) {
        Pump-Ports
        Start-Sleep -Milliseconds 10
    }
    $stopReason = "completed"
}
catch {
    $stopReason = "error"
    $errorText = $_.Exception.ToString()
}
finally {
    if ($hostPort.IsOpen) { $hostPort.Close() }
    if ($debugPort.IsOpen) { $debugPort.Close() }
    $eventWriter.Dispose()
    $debugWriter.Dispose()
}

$rxStats = @([regex]::Matches($debugBuffer, 'RXSTAT[^\r\n]*') | ForEach-Object { $_.Value })
$result = [ordered]@{
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    diagnostic_only = $true
    reset_skipped = [bool]$SkipReset
    stop_reason = $stopReason
    error = $errorText
    hello3_count = $hello3
    nav_packets = @($navPackets)
    trigger_observed = $triggered
    frames_sent = $framesSent
    frame_limit = 2
    byte_pacing_override = $false
    expected_physical_sequence = "alternating full cells 1,3,5,7,9 then clear all cells"
    rx_stats = $rxStats
    debug_contains_format_error = $debugBuffer.Contains("FRAME FORMAT ERROR")
    debug_contains_pca_init_ok = $debugBuffer.Contains("PCA INIT OK")
    debug_log = $debugPath
    serial_log = $eventPath
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding UTF8
[IO.File]::WriteAllText($donePath, ($result | ConvertTo-Json -Depth 6), $utf8)
$result | ConvertTo-Json -Depth 6
