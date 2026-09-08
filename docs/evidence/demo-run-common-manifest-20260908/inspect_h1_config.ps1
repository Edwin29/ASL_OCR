$ErrorActionPreference = 'Stop'
$root = 'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944\config'
$items = Get-ChildItem -LiteralPath $root -File -Recurse | ForEach-Object {
    [pscustomobject]@{
        relative = $_.FullName.Substring($root.Length + 1)
        length = $_.Length
    }
}
$items | ConvertTo-Json -Compress
