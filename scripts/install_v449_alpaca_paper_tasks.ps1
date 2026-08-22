$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -WakeToRun

$runnerScript = Join-Path $repo "scripts\run_v449_alpaca_paper.ps1"
$runnerAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runnerScript`""
$runnerTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "20:00"
Register-ScheduledTask `
    -TaskName "USIntradayLab-V449-AlpacaPaper" `
    -Description "Frozen v449 Alpaca Paper Trading runner; paper endpoint only." `
    -Action $runnerAction `
    -Trigger $runnerTrigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

$closeScript = Join-Path $repo "scripts\close_v449_alpaca_paper.ps1"
$closeAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$closeScript`""
$closeTriggerDst = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday `
    -At "03:45"
$closeTriggerStandard = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday `
    -At "04:45"
Register-ScheduledTask `
    -TaskName "USIntradayLab-V449-AlpacaPaper-Closeout" `
    -Description "Independent DST-safe late-session closeout for v449 Alpaca paper positions." `
    -Action $closeAction `
    -Trigger @($closeTriggerDst, $closeTriggerStandard) `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null
