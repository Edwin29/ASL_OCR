param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Programmer,
    [string] $ProbeSerial = "0670FF485775495067203341",
    [int] $CaptureSeconds = 15
)

$ErrorActionPreference = "Stop"
$logs = Join-Path $RunRoot "logs"
$reports = Join-Path $RunRoot "reports"
New-Item -ItemType Directory -Path $logs, $reports -Force | Out-Null

$eventPath = Join-Path $logs "firmware-smoke-serial.jsonl"
$debugPath = Join-Path $logs "firmware-smoke-com5.txt"
$resetPath = Join-Path $logs "firmware-smoke-reset.log"
$resultPath = Join-Path $reports "firmware-smoke.json"

$utf8 = New-Object System.Text.UTF8Encoding($false)
$eventWriter = New-Object System.IO.StreamWriter($eventPath, $false, $utf8)
$eventWriter.AutoFlush = $true
$debugWriter = New-Object System.IO.StreamWriter($debugPath, $false, $utf8)
$debugWriter.AutoFlush = $true

function Write-SerialEvent {
    param([string] $Direction, [string] $Port, [byte[]] $Bytes)
    $record = [ordered]@{
        at_utc = (Get-Date).ToUniversalTime().ToString("o")
        direction = $Direction
        port = $Port
        length = $Bytes.Length
        hex = [BitConverter]::ToString($Bytes).Replace("-", "").ToLowerInvariant()
        ascii = [Text.Encoding]::ASCII.GetString($Bytes)
    }
    $eventWriter.WriteLine(($record | ConvertTo-Json -Compress))
}

$debug = New-Object System.IO.Ports.SerialPort("COM5", 115200, "None", 8, "One")
$hostPort = New-Object System.IO.Ports.SerialPort("COM9", 9600, "None", 8, "One")
$debug.ReadTimeout = 50
$hostPort.ReadTimeout = 50
$hostPort.WriteTimeout = 500
$debugBuffer = ""
$hostBuffer = ""
$hello3 = 0
$helloAck = 0
$modePackets = 0
$navAcks = 0
$unexpectedHostFrames = 0
$resetExit = $null

try {
    $debug.Open()
    $hostPort.Open()

    & $Programmer -c "port=SWD" "sn=$ProbeSerial" -rst *> $resetPath
    $resetExit = $LASTEXITCODE

    $deadline = [DateTime]::UtcNow.AddSeconds($CaptureSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($debug.BytesToRead -gt 0) {
            $buffer = New-Object byte[] ([Math]::Min(4096, $debug.BytesToRead))
            $count = $debug.Read($buffer, 0, $buffer.Length)
            if ($count -gt 0) {
                $bytes = $buffer[0..($count - 1)]
                Write-SerialEvent "rx" "COM5" $bytes
                $text = [Text.Encoding]::ASCII.GetString($bytes)
                $debugBuffer += $text
                $debugWriter.Write($text)
            }
        }

        if ($hostPort.BytesToRead -gt 0) {
            $buffer = New-Object byte[] ([Math]::Min(4096, $hostPort.BytesToRead))
            $count = $hostPort.Read($buffer, 0, $buffer.Length)
            if ($count -gt 0) {
                $bytes = $buffer[0..($count - 1)]
                Write-SerialEvent "rx" "COM9" $bytes
                $hostBuffer += [Text.Encoding]::ASCII.GetString($bytes)
                while ($hostBuffer.Contains("`n")) {
                    $newline = $hostBuffer.IndexOf("`n")
                    $line = $hostBuffer.Substring(0, $newline).TrimEnd("`r")
                    $hostBuffer = $hostBuffer.Substring($newline + 1)
                    if ($line -eq "HELLO,3") {
                        $hello3++
                        $payload = [Text.Encoding]::ASCII.GetBytes("ACK,HELLO,3`n")
                        $hostPort.Write($payload, 0, $payload.Length)
                        Write-SerialEvent "tx" "COM9" $payload
                        $helloAck++
                    }
                    elseif ($line -match '^NAV,V,([AR]),([0-9]+)$') {
                        $modePackets++
                        $payload = [Text.Encoding]::ASCII.GetBytes("ACK,$($Matches[2])`n")
                        $hostPort.Write($payload, 0, $payload.Length)
                        Write-SerialEvent "tx" "COM9" $payload
                        $navAcks++
                    }
                }
            }
        }
        Start-Sleep -Milliseconds 10
    }
}
finally {
    if ($hostPort.IsOpen) { $hostPort.Close() }
    if ($debug.IsOpen) { $debug.Close() }
    $eventWriter.Dispose()
    $debugWriter.Dispose()
}

$result = [ordered]@{
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    reset_exit_code = $resetExit
    hello3_count = $hello3
    hello3_ack_count = $helloAck
    initial_mode_packet_count = $modePackets
    initial_mode_ack_count = $navAcks
    pca_0x40_found = $debugBuffer.Contains("PCA 0x40 FOUND")
    pca_0x41_found = $debugBuffer.Contains("PCA 0x41 FOUND")
    pca_init_ok = $debugBuffer.Contains("PCA INIT OK")
    v3_connected_debug = $debugBuffer.Contains("BT: HOST CONNECTED (V3 EDGES)")
    host_frames_sent = $unexpectedHostFrames
    event_log = $eventPath
    debug_log = $debugPath
    reset_log = $resetPath
    pass = ($resetExit -eq 0 -and $hello3 -ge 1 -and $helloAck -eq $hello3 -and $modePackets -eq 1 -and $navAcks -eq 1 -and $debugBuffer.Contains("PCA 0x40 FOUND") -and $debugBuffer.Contains("PCA 0x41 FOUND") -and $debugBuffer.Contains("PCA INIT OK") -and $debugBuffer.Contains("BT: HOST CONNECTED (V3 EDGES)"))
}
$result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
$result | ConvertTo-Json
