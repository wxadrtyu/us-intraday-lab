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
    -TaskName "USIntradayLab-V247-V449-V798-AlpacaPaperPool" `
    -Description "Frozen equal-capital v247/v449/v798 Alpaca Paper pool; gross <= 0.99." `
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
    -TaskName "USIntradayLab-V247-V449-V798-AlpacaPaperPool-Closeout" `
    -Description "DST-safe closeout for the v247/v449/v798 Alpaca Paper pool." `
    -Action $closeAction `
    -Trigger @($closeTriggerDst, $closeTriggerStandard) `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Disable-ScheduledTask -TaskName "USIntradayLab-V247-V449-AlpacaPaperPool" -ErrorAction SilentlyContinue | Out-Null
Disable-ScheduledTask -TaskName "USIntradayLab-V247-V449-AlpacaPaperPool-Closeout" -ErrorAction SilentlyContinue | Out-Null
Disable-ScheduledTask -TaskName "USIntradayLab-V449-AlpacaPaper" -ErrorAction SilentlyContinue | Out-Null
Disable-ScheduledTask -TaskName "USIntradayLab-V449-AlpacaPaper-Closeout" -ErrorAction SilentlyContinue | Out-Null
