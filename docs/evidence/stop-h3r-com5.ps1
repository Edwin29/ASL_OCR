$matches = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*h3r-com5-physical-down-logger.py*' }
$matches | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3
foreach($p in $matches){ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
$log='C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output\logs\h3r-physical-down-com5.jsonl'
Get-FileHash -Algorithm SHA256 -LiteralPath $log | Select-Object Algorithm,Hash,Path | ConvertTo-Json
