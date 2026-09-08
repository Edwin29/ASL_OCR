param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [int] $CaptureSeconds = 900,
    [int] $MaxNavPackets = 16,
    [int] $ReadyAfterHello3Count = 1,
    [ValidatePattern('^[UDLRNPCV]$')] [string] $RequiredControl = "U",
    [ValidatePattern('^[ASRL]$')] [string] $RequiredAction = "S",
    [int] $RequiredUniqueControlCount = 0
)

$ErrorActionPreference = "Stop"
if ($ReadyAfterHello3Count -lt 1) {
    throw "ReadyAfterHello3Count must be at least 1."
}
if ($RequiredUniqueControlCount -lt 0) {
    throw "RequiredUniqueControlCount must not be negative."
}
$minimumPacketCapacity = $ReadyAfterHello3Count + $RequiredUniqueControlCount
if ($MaxNavPackets -lt $minimumPacketCapacity) {
    throw "MaxNavPackets must be at least ReadyAfterHello3Count + RequiredUniqueControlCount ($minimumPacketCapacity)."
}
$logs = Join-Path $RunRoot "logs"
$reports = Join-Path $RunRoot "reports"
$controlRoot = Join-Path $RunRoot "physical-controls"
New-Item -ItemType Directory -Path $logs, $reports, $controlRoot -Force | Out-Null

$eventPath = Join-Path $logs "physical-controls-serial.jsonl"
$debugPath = Join-Path $logs "physical-controls-com5.txt"
$portsOpenPath = Join-Path $controlRoot "ports-open"
$readyPath = Join-Path $controlRoot "ready"
$stopPath = Join-Path $controlRoot "stop"
$donePath = Join-Path $controlRoot "done"
$resultPath = Join-Path $reports "physical-controls-capture.json"

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

$debugPort = New-Object System.IO.Ports.SerialPort("COM5", 115200, "None", 8, "One")
$hostPort = New-Object System.IO.Ports.SerialPort("COM9", 9600, "None", 8, "One")
$debugPort.ReadTimeout = 50
$hostPort.ReadTimeout = 50
$hostPort.WriteTimeout = 500
$hostBuffer = ""
$debugBuffer = ""
$navPackets = New-Object System.Collections.Generic.List[string]
$requiredSequences = New-Object 'System.Collections.Generic.HashSet[uint32]'
$hello3 = 0
$acks = 0
$observationReady = $false
$observationReadyAtUtc = $null
$requiredModeSeen = $false
$stopReason = "timeout"
$errorText = $null

try {
    $debugPort.Open()
    $hostPort.Open()
    [IO.File]::WriteAllText($portsOpenPath, (Get-Date).ToUniversalTime().ToString("o"), $utf8)
    $deadline = [DateTime]::UtcNow.AddSeconds($CaptureSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $stopPath) {
            $stopReason = "requested"
            break
        }
        if ($navPackets.Count -ge $MaxNavPackets) {
            $stopReason = "max_nav_packets"
            break
        }

        if ($debugPort.BytesToRead -gt 0) {
            $buffer = New-Object byte[] ([Math]::Min(4096, $debugPort.BytesToRead))
            $count = $debugPort.Read($buffer, 0, $buffer.Length)
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
                        if ($hello3 -ge $ReadyAfterHello3Count) {
                            $requiredModeSeen = $false
                        }
                        $payload = [Text.Encoding]::ASCII.GetBytes("ACK,HELLO,3`n")
                        $hostPort.Write($payload, 0, $payload.Length)
                        Write-SerialEvent "tx" "COM9" $payload
                    }
                    elseif ($line -match '^NAV,([UDLRNPCV]),([ASRL]),([0-9]+)$') {
                        $control = $Matches[1]
                        $action = $Matches[2]
                        $sequence = [uint32]$Matches[3]
                        $navPackets.Add($line)
                        $payload = [Text.Encoding]::ASCII.GetBytes("ACK,$sequence`n")
                        $hostPort.Write($payload, 0, $payload.Length)
                        Write-SerialEvent "tx" "COM9" $payload
                        $acks++
                        if ($hello3 -ge $ReadyAfterHello3Count -and $control -eq "V") {
                            $requiredModeSeen = $true
                            if (-not $observationReady) {
                                $observationReady = $true
                                $observationReadyAtUtc = (Get-Date).ToUniversalTime().ToString("o")
                                [IO.File]::WriteAllText($readyPath, $observationReadyAtUtc, $utf8)
                            }
                        }
                        elseif ($observationReady -and
                                $control -eq $RequiredControl -and
                                $action -eq $RequiredAction) {
                            [void]$requiredSequences.Add($sequence)
                        }
                    }
                }
            }
        }
        if ($RequiredUniqueControlCount -gt 0 -and
            $requiredSequences.Count -ge $RequiredUniqueControlCount) {
            $stopReason = "required_unique_controls"
            break
        }
        Start-Sleep -Milliseconds 10
    }
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
    stop_reason = $stopReason
    error = $errorText
    hello3_count = $hello3
    observation_ready = $observationReady
    observation_ready_at_utc = $observationReadyAtUtc
    required_mode_seen = $requiredModeSeen
    nav_packet_count = $navPackets.Count
    ack_count = $acks
    nav_packets = @($navPackets)
    host_frames_sent = 0
    max_nav_packets = $MaxNavPackets
    ready_after_hello3_count = $ReadyAfterHello3Count
    required_control = $RequiredControl
    required_action = $RequiredAction
    required_unique_control_count = $RequiredUniqueControlCount
    observed_unique_control_count = $requiredSequences.Count
    observed_unique_sequences = @($requiredSequences | Sort-Object)
    event_log = $eventPath
    debug_log = $debugPath
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding UTF8
[IO.File]::WriteAllText($donePath, ($result | ConvertTo-Json -Depth 5), $utf8)
$result | ConvertTo-Json -Depth 5
