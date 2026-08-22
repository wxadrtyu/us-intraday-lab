$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$workspacePython = Join-Path $repo ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $workspacePython) {
    $workspacePython
} else {
    (Get-Command python.exe -ErrorAction Stop).Source
}
Set-Location -LiteralPath $repo
$env:PYTHONPATH = "$repo;$repo\scripts;$repo\src"
$logDirectory = Join-Path $repo "state\paper\logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$log = Join-Path $logDirectory "v449-runner.log"
& $python "scripts\run_v449_alpaca_paper.py" 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
exit $code
