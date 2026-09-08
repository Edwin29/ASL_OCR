param(
    [Parameter(Mandatory = $true)] [string] $RunRoot,
    [Parameter(Mandatory = $true)] [string] $Programmer,
    [string] $ProbeSerial = "0670FF485775495067203341"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path (Join-Path $RunRoot "logs"), (Join-Path $RunRoot "reports") -Force | Out-Null
$serialPath = Join-Path $RunRoot "logs\serial.jsonl"
$debugPath = Join-Path $RunRoot "logs\com5.txt"
$resetPath = Join-Path $RunRoot "logs\reset.log"
$writer = New-Object IO.StreamWriter($serialPath, $false, (New-Object Text.UTF8Encoding($false)))
$writer.AutoFlush = $true
$debugWriter = New-Object IO.StreamWriter($debugPath, $false, (New-Object Text.UTF8Encoding($false)))
$debugWriter.AutoFlush = $true

function Log-Bytes([string] $direction, [string] $port, [byte[]] $bytes, [string] $role) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
    $writer.WriteLine(([ordered]@{at_utc=(Get-Date).ToUniversalTime().ToString("o");direction=$direction;port=$port;role=$role;length=$bytes.Length;sha256=$digest;hex=[BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant();ascii=[Text.Encoding]::ASCII.GetString($bytes)} | ConvertTo-Json -Compress))
}

$debugPort = New-Object IO.Ports.SerialPort("COM5", 115200, "None", 8, "One")
$hostPort = New-Object IO.Ports.SerialPort("COM9", 9600, "None", 8, "One")
$hostPort.WriteTimeout = 500
$hostBuffer = ""
$debugText = ""
$hello3 = 0
$navAcks = 0
$resetExit = $null
$clearSent = $false
$errorText = $null

function Pump {
    if ($debugPort.BytesToRead -gt 0) {
        $b = New-Object byte[] ([Math]::Min(4096, $debugPort.BytesToRead))
        $n = $debugPort.Read($b, 0, $b.Length)
        if ($n -gt 0) {
            $bytes = $b[0..($n-1)]
            Log-Bytes "rx" "COM5" $bytes "debug"
            $text = [Text.Encoding]::ASCII.GetString($bytes)
            $script:debugText += $text
            $debugWriter.Write($text)
        }
    }
    if ($hostPort.BytesToRead -gt 0) {
        $b = New-Object byte[] ([Math]::Min(4096, $hostPort.BytesToRead))
        $n = $hostPort.Read($b, 0, $b.Length)
        if ($n -gt 0) {
            $bytes = $b[0..($n-1)]
            Log-Bytes "rx" "COM9" $bytes "firmware_to_host"
            $script:hostBuffer += [Text.Encoding]::ASCII.GetString($bytes)
            while ($script:hostBuffer.Contains("`n")) {
                $i = $script:hostBuffer.IndexOf("`n")
                $line = $script:hostBuffer.Substring(0,$i).TrimEnd("`r")
                $script:hostBuffer = $script:hostBuffer.Substring($i+1)
                if ($line -eq "HELLO,3") {
                    $script:hello3++
                    $payload=[Text.Encoding]::ASCII.GetBytes("ACK,HELLO,3`n")
                    $hostPort.Write($payload,0,$payload.Length); Log-Bytes "tx" "COM9" $payload "handshake_ack"
                } elseif ($line -match '^NAV,([UDLRNPCV]),([ASRL]),([0-9]+)$') {
                    $payload=[Text.Encoding]::ASCII.GetBytes("ACK,$($Matches[3])`n")
                    $hostPort.Write($payload,0,$payload.Length); Log-Bytes "tx" "COM9" $payload "nav_ack"; $script:navAcks++
                }
            }
        }
    }
}

try {
    $debugPort.Open(); $hostPort.Open()
    & $Programmer -c "port=SWD" "sn=$ProbeSerial" -rst *> $resetPath
    $resetExit = $LASTEXITCODE
    $until=[DateTime]::UtcNow.AddSeconds(5)
    while([DateTime]::UtcNow -lt $until){Pump;Start-Sleep -Milliseconds 10}
    if($hello3 -lt 1){throw "HELLO,3 not observed"}
    $payload=[Text.Encoding]::ASCII.GetBytes("FRAME,0,17,0,0,112,0,0,0,0,0,0,0,0,0,0`n")
    foreach($byte in $payload){$one=[byte[]]@($byte);$hostPort.Write($one,0,1);Log-Bytes "tx" "COM9" $one "paced_clear_byte";Start-Sleep -Milliseconds 20}
    $clearSent=$true
    $until=[DateTime]::UtcNow.AddSeconds(6)
    while([DateTime]::UtcNow -lt $until){Pump;Start-Sleep -Milliseconds 10}
} catch { $errorText=$_.Exception.ToString() }
finally {
    if($hostPort.IsOpen){$hostPort.Close()};if($debugPort.IsOpen){$debugPort.Close()};$writer.Dispose();$debugWriter.Dispose()
}

$result=[ordered]@{captured_at_utc=(Get-Date).ToUniversalTime().ToString("o");reset_exit_code=$resetExit;hello3_count=$hello3;nav_ack_count=$navAcks;clear_sent=$clearSent;frame_count=if($clearSent){1}else{0};byte_interval_ms=20;normal_rate_acceptance=$false;format_error=$debugText.Contains("FRAME FORMAT ERROR");generation_112_seen=$debugText.Contains("GEN    = 112");error=$errorText;serial_log=$serialPath;debug_log=$debugPath}
$result|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $RunRoot "reports\result.json") -Encoding UTF8
$result|ConvertTo-Json
