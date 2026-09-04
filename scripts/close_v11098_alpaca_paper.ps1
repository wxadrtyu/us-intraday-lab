$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python.exe -ErrorAction Stop).Source }
Set-Location -LiteralPath $repo
$env:PYTHONPATH = "$repo;$repo\scripts;$repo\src"
& $python "scripts\close_v11098_alpaca_paper.py"
exit $LASTEXITCODE
