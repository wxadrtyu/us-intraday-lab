[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DataRoot,
    [Parameter(Mandatory)][int]$DailyProcessId,
    [Parameter(Mandatory)][string]$DailyStdout,
    [Parameter(Mandatory)][string]$DailyStderr,
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

while (Get-Process -Id $DailyProcessId -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 30
}

if ((Get-Item -LiteralPath $DailyStderr).Length -ne 0) {
    throw "Corrected daily acquisition wrote stderr: $DailyStderr"
}
$dailyResult = Get-Content -LiteralPath $DailyStdout -Tail 1 | ConvertFrom-Json
if ($dailyResult.status -ne 'COMPLETE') {
    throw "Corrected daily acquisition did not finish cleanly: $DailyStdout"
}

$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$universeScript = Join-Path $RepoRoot 'scripts\build_us_market_monthly_universe.py'
$minuteScript = Join-Path $RepoRoot 'scripts\acquire_us_market_minutes.py'

$universeOutput = & python $universeScript `
    --root $DataRoot `
    --start-month 2021-01-01 `
    --end-month 2026-09-01
if ($LASTEXITCODE -ne 0) {
    throw 'Point-in-time monthly universe construction failed.'
}
$universe = $universeOutput | Select-Object -Last 1 | ConvertFrom-Json
$decisions = Join-Path $DataRoot (
    'data\catalog\monthly_universe\' + $universe.dataset_id + '\decisions.parquet'
)
Write-Output $universeOutput

& python $minuteScript --root $DataRoot --decisions $decisions --batch-size 25
if ($LASTEXITCODE -ne 0) {
    throw 'Dynamic full-market minute acquisition failed.'
}
