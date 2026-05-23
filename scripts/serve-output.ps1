$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutputDir = Join-Path $Root "outputs"
$Port = 8787

Set-Location -LiteralPath $OutputDir

$ip = Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -notlike "127.*" -and
    $_.IPAddress -notlike "169.254.*" -and
    $_.PrefixOrigin -ne "WellKnown"
  } |
  Select-Object -First 1 -ExpandProperty IPAddress

Write-Host "Serving subscription files from: $OutputDir"
Write-Host "PC URL:     http://127.0.0.1:$Port/quality.yaml"
if ($ip) {
  Write-Host "Phone URL:  http://$ip`:$Port/quality.yaml"
}
Write-Host "Keep this window open while using the phone URL."

python -m http.server $Port --bind 0.0.0.0
