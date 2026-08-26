$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$repo;$repo\scripts;$repo\src"
$workspacePython = Join-Path $repo ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $workspacePython) { $workspacePython } else { (Get-Command python.exe -ErrorAction Stop).Source }
& $python -c "from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker; b=AlpacaPaperBroker.from_environment(); assert not b.positions() and not b.open_orders(), 'CONSOLIDATION_REQUIRES_FLAT_PAPER_ACCOUNT'"
if ($LASTEXITCODE -ne 0) { throw "Paper account preflight failed" }

$legacyNames = @(
    "USIntradayLab-V449-AlpacaPaper",
    "USIntradayLab-V449-AlpacaPaper-Closeout",
    "USIntradayLab-V247-V449-AlpacaPaperPool",
    "USIntradayLab-V247-V449-AlpacaPaperPool-Closeout",
    "USIntradayLab-V247-V449-V798-AlpacaPaperPool",
    "USIntradayLab-V247-V449-V798-AlpacaPaperPool-Closeout",
    "USIntradayLab-V247-V449-V798-V1254-AlpacaPaperPool",
    "USIntradayLab-V247-V449-V798-V1254-AlpacaPaperPool-Closeout"
)
$legacyTasks = @($legacyNames | ForEach-Object { Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue })
if (@($legacyTasks | Where-Object { $_.State -eq "Running" }).Count -gt 0) {
    throw "Do not switch while a legacy task is running"
}
$enabledBefore = @($legacyTasks | Where-Object { $_.Settings.Enabled } | Select-Object -ExpandProperty TaskName)
$backupDirectory = Join-Path $repo ("state\backups\v1254-task-consolidation-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupDirectory | Out-Null
foreach ($task in $legacyTasks) {
    Export-ScheduledTask -TaskName $task.TaskName | Out-File -LiteralPath (Join-Path $backupDirectory ($task.TaskName + ".xml")) -Encoding utf8
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 8) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -WakeToRun
$settings.Enabled = $false
$entryName = "USIntradayLab-V1254-AlpacaPaper"
$closeName = "USIntradayLab-V1254-AlpacaPaper-Closeout"
if (Get-ScheduledTask -TaskName $entryName,$closeName -ErrorAction SilentlyContinue) {
    throw "Consolidated tasks already exist; inspect instead of overwriting"
}
try {
    $runnerScript = Join-Path $repo "scripts\run_v449_alpaca_paper.ps1"
    $entryAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runnerScript`""
    $entryTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "20:00"
    Register-ScheduledTask -TaskName $entryName -Description "User-consolidated frozen v1254 Paper representative; total gross <= 0.99; inherited exception labels retained." -Action $entryAction -Trigger $entryTrigger -Principal $principal -Settings $settings | Out-Null

    $closeScript = Join-Path $repo "scripts\close_v449_alpaca_paper.ps1"
    $closeAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$closeScript`""
    $closeDst = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At "03:45"
    $closeStandard = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At "04:45"
    Register-ScheduledTask -TaskName $closeName -Description "Unchanged DST-safe closeout for active and historical Paper pool orders." -Action $closeAction -Trigger @($closeDst,$closeStandard) -Principal $principal -Settings $settings | Out-Null
    foreach ($task in $legacyTasks) { Disable-ScheduledTask -TaskName $task.TaskName | Out-Null }
    Enable-ScheduledTask -TaskName $entryName | Out-Null
    Enable-ScheduledTask -TaskName $closeName | Out-Null
} catch {
    Get-ScheduledTask -TaskName $entryName,$closeName -ErrorAction SilentlyContinue | Disable-ScheduledTask | Out-Null
    foreach ($name in $enabledBefore) { Enable-ScheduledTask -TaskName $name | Out-Null }
    throw
}
Write-Output "Consolidation complete; original task XML backups: $backupDirectory"
Get-ScheduledTask -TaskName $entryName,$closeName | Select-Object TaskName,State
