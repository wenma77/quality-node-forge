$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
  python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .

.\.venv\Scripts\python.exe -m quality_node_forge run `
  --candidate-limit 717 `
  --top 30 `
  --rounds 3 `
  --workers 20 `
  --timeout-ms 5000 `
  --max-delay-ms 1800 `
  --max-jitter-ms 700 `
  --min-success-rate 1.0

.\tools\mihomo\mihomo.exe -t -d runtime -f outputs\quality.yaml
