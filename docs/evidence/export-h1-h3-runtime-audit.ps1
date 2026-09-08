$roots = @(
  'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-223731',
  'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944',
  'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639',
  'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3-20260908-001800',
  'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output'
)
$result = foreach ($root in $roots) {
  $files = if (Test-Path -LiteralPath $root) {
    @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Extension -in @('.toml','.ps1','.bat','.cmd','.py','.json') } |
      ForEach-Object { $_.FullName })
  } else { @() }
  [pscustomobject]@{ root=$root; files=$files }
}
$result | ConvertTo-Json -Depth 4
