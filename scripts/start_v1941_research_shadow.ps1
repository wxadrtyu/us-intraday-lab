param(
    [Parameter(Mandatory=$true)][string]$Session
)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$sessionDate = [datetime]::ParseExact($Session, 'yyyy-MM-dd', $null)
$outputPath = Join-Path $repoPath 'state\research_shadow_v1941'
$sessionPath = Join-Path $outputPath $Session
New-Item -ItemType Directory -Force -Path $sessionPath | Out-Null
if (-not $env:ALPACA_PAPER_API_KEY -or -not $env:ALPACA_PAPER_SECRET_KEY) {
    throw 'ACTIVE_MARKET_DATA_CREDENTIALS_MISSING'
}
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$env:PYTHONPATH = "$repoPath;$repoPath\scripts;$repoPath\src"
$stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$process = Start-Process -FilePath $pythonPath -ArgumentList @(
    '-u', "`"$PSScriptRoot\run_v1941_research_shadow.py`"",
    '--session', $sessionDate.ToString('yyyy-MM-dd'), '--output', "`"$outputPath`""
) -WorkingDirectory $repoPath -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $sessionPath "$stamp.stdout.log") `
  -RedirectStandardError (Join-Path $sessionPath "$stamp.stderr.log")
[pscustomobject]@{ ProcessId=$process.Id; Session=$Session; OrderRoute='FORBIDDEN'; Output=$sessionPath }
