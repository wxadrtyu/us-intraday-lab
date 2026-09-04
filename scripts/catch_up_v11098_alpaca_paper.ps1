$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python.exe -ErrorAction Stop).Source }
Set-Location -LiteralPath $repo
$env:PYTHONPATH = "$repo;$repo\scripts;$repo\src"
$logDirectory = Join-Path $repo "state\paper\logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
& $python "scripts\catch_up_v11098_alpaca_paper.py" 2>&1 | Tee-Object -FilePath (Join-Path $logDirectory "v11098-catch-up.log") -Append
exit $LASTEXITCODE
