$ErrorActionPreference = 'Stop'
$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944'
Get-ChildItem -LiteralPath $root -File |
    Select-Object Name, Length |
    ConvertTo-Json -Compress
