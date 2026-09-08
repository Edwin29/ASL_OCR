param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Programmer,
    [string] $ProbeSerial = "0670FF485775495067203341",
    [int] $TriggerWaitSeconds = 600,
    [switch] $SkipReset,
    [ValidateSet("Basic", "CellIsolation", "Cell1Isolation", "SpanRoleSample")] [string] $Profile = "Basic",
    [ValidateRange(1000, 30000)] [int] $CellIsolationDelayMs = 5000
)

$ErrorActionPreference = "Stop"
$logs = Join-Path $RunRoot "logs"
$reports = Join-Path $RunRoot "reports"
$controlRoot = Join-Path $RunRoot "control"
New-Item -ItemType Directory -Path $logs, $reports, $controlRoot -Force | Out-Null

$eventPath = Join-Path $logs "serial.jsonl"
$debugPath = Join-Path $logs "com5.txt"
$resetPath = Join-Path $logs "reset.log"
$readyPath = Join-Path $controlRoot "ready-for-trigger"
$triggerPath = Join-Path $controlRoot "trigger"
$donePath = Join-Path $controlRoot "done"
$resultPath = Join-Path $reports "result.json"

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
    $record = [ordered]@{
        at_utc = (Get-Date).ToUniversalTime().ToString("o")
        direction = $Direction
        port = $Port
        role = $Role
        length = $Bytes.Length
        sha256 = $digest
        hex = [BitConverter]::ToString($Bytes).Replace("-", "").ToLowerInvariant()
        ascii = [Text.Encoding]::ASCII.GetString($Bytes)
    }
    $eventWriter.WriteLine(($record | ConvertTo-Json -Compress))
}

if ($Profile -eq "SpanRoleSample") {
    $frames = @(
        "FRAME,0,50,0,0,150,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,51,0,0,151,0,0,0,0,7,0,0,0,0,0`n",
        "FRAME,0,52,0,0,152,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,53,0,0,153,0,0,0,0,56,0,0,0,0,0`n",
        "FRAME,0,54,0,0,154,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,55,0,0,155,0,0,0,0,0,0,0,0,0,7`n",
        "FRAME,0,56,0,0,156,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,57,0,0,157,0,0,0,0,0,0,0,0,0,56`n",
        "FRAME,0,58,0,0,158,0,0,0,0,0,0,0,0,0,0`n"
    )
    $interFrameDelayMs = $CellIsolationDelayMs
}
elseif ($Profile -eq "Cell1Isolation") {
    $frames = @(
        "FRAME,0,40,0,0,140,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,41,0,0,141,7,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,42,0,0,142,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,43,0,0,143,56,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,44,0,0,144,0,0,0,0,0,0,0,0,0,0`n"
    )
    $interFrameDelayMs = $CellIsolationDelayMs
}
elseif ($Profile -eq "CellIsolation") {
    $frames = @(
        "FRAME,0,30,0,0,130,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,31,0,0,131,63,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,32,0,0,132,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,33,0,0,133,0,7,0,0,0,0,0,0,0,0`n",
        "FRAME,0,34,0,0,134,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,35,0,0,135,0,56,0,0,0,0,0,0,0,0`n",
        "FRAME,0,36,0,0,136,0,0,0,0,0,0,0,0,0,0`n"
    )
    $interFrameDelayMs = $CellIsolationDelayMs
}
else {
    $frames = @(
        "FRAME,0,16,0,0,110,11,38,45,52,18,18,54,55,60,1`n",
        "FRAME,0,16,0,0,110,11,38,45,52,18,18,54,55,60,1`n",
        "FRAME,0,17,0,0,111,0,0,0,0,0,0,0,0,0,0`n",
        "FRAME,0,17,0,0,111,0,0,0,0,0,0,0,0,0,0`n"
    )
    $interFrameDelayMs = 3000
}

$debugPort = New-Object System.IO.Ports.SerialPort("COM5", 115200, "None", 8, "One")
$hostPort = New-Object System.IO.Ports.SerialPort("COM9", 9600, "None", 8, "One")
$debugPort.ReadTimeout = 50
$hostPort.ReadTimeout = 50
$hostPort.WriteTimeout = 500
$hostBuffer = ""
$debugBuffer = ""
$hello3 = 0
$navPackets = New-Object System.Collections.Generic.List[string]
$navAcks = 0
$framesSent = 0
$triggered = $false
$resetExit = $null
$stopReason = "timeout_waiting_for_trigger"
$errorText = $null

function Pump-Ports {
    if ($debugPort.BytesToRead -gt 0) {
        $buffer = New-Object byte[] ([Math]::Min(4096, $debugPort.BytesToRead))
        $count = $debugPort.Read($buffer, 0, $buffer.Length)
        if ($count -gt 0) {
            $bytes = $buffer[0..($count - 1)]
            Write-SerialEvent "rx" "COM5" $bytes "debug"
            $script:debugBuffer += [Text.Encoding]::ASCII.GetString($bytes)
            $debugWriter.Write([Text.Encoding]::ASCII.GetString($bytes))
        }
    }
    if ($hostPort.BytesToRead -gt 0) {
        $buffer = New-Object byte[] ([Math]::Min(4096, $hostPort.BytesToRead))
        $count = $hostPort.Read($buffer, 0, $buffer.Length)
        if ($count -gt 0) {
            $bytes = $buffer[0..($count - 1)]
            Write-SerialEvent "rx" "COM9" $bytes "firmware_to_host"
            $script:hostBuffer += [Text.Encoding]::ASCII.GetString($bytes)
            while ($script:hostBuffer.Contains("`n")) {
                $newline = $script:hostBuffer.IndexOf("`n")
                $line = $script:hostBuffer.Substring(0, $newline).TrimEnd("`r")
                $script:hostBuffer = $script:hostBuffer.Substring($newline + 1)
                if ($line -eq "HELLO,3") {
                    $script:hello3++
                    $payload = [Text.Encoding]::ASCII.GetBytes("ACK,HELLO,3`n")
                    $hostPort.Write($payload, 0, $payload.Length)
                    Write-SerialEvent "tx" "COM9" $payload "handshake_ack"
                }
                elseif ($line -match '^NAV,([UDLRNPCV]),([ASRL]),([0-9]+)$') {
                    $script:navPackets.Add($line)
                    $payload = [Text.Encoding]::ASCII.GetBytes("ACK,$($Matches[3])`n")
                    $hostPort.Write($payload, 0, $payload.Length)
                    Write-SerialEvent "tx" "COM9" $payload "nav_ack"
                    $script:navAcks++
                }
            }
        }
    }
}

try {
    $debugPort.Open()
    $hostPort.Open()
    if ($SkipReset) {
        [IO.File]::WriteAllText($resetPath, "reset skipped; using the verified reset performed by candidate flash", $utf8)
        $resetExit = 0
    }
    else {
        & $Programmer -c "port=SWD" "sn=$ProbeSerial" -rst *> $resetPath
        $resetExit = $LASTEXITCODE
        if ($resetExit -ne 0) { throw "STM32 reset failed with exit code $resetExit" }
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
        $payload = [Text.Encoding]::ASCII.GetBytes($frame)
        $hostPort.Write($payload, 0, $payload.Length)
        Write-SerialEvent "tx" "COM9" $payload "frame"
        $framesSent++
        $until = [DateTime]::UtcNow.AddMilliseconds($interFrameDelayMs)
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

$result = [ordered]@{
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    reset_skipped = [bool]$SkipReset
    stop_reason = $stopReason
    error = $errorText
    reset_exit_code = $resetExit
    hello3_count = $hello3
    nav_packets = @($navPackets)
    nav_ack_count = $navAcks
    trigger_observed = $triggered
    profile = $Profile
    frames_sent = $framesSent
    frame_limit = $frames.Count
    inter_frame_delay_ms = $interFrameDelayMs
    byte_pacing_override = $false
    debug_contains_format_error = $debugBuffer.Contains("FRAME FORMAT ERROR")
    debug_contains_pca_init_ok = $debugBuffer.Contains("PCA INIT OK")
    debug_log = $debugPath
    serial_log = $eventPath
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding UTF8
[IO.File]::WriteAllText($donePath, ($result | ConvertTo-Json -Depth 5), $utf8)
$result | ConvertTo-Json -Depth 5
