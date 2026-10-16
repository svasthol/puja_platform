# Register Windows Scheduled Task: staging terraform apply every N minutes (when PC is on).
param(
    [int]$IntervalMinutes = 15
)

if ($IntervalMinutes -lt 1 -or $IntervalMinutes -gt 1439) {
    Write-Error "IntervalMinutes must be 1-1439."
    exit 1
}

$TaskName = "ManaGuruji-StagingTerraformRetry"
$ScriptPath = (Resolve-Path (Join-Path $PSScriptRoot "Invoke-StagingTerraformApplyOnce.ps1")).Path
$WorkDir = (Resolve-Path $PSScriptRoot).Path
$PsExe = (Get-Command powershell.exe).Source

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# RepetitionDuration max ~31 days (Task Scheduler limit); re-run this script monthly if needed.
$Action = New-ScheduledTaskAction `
    -Execute $PsExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`"" `
    -WorkingDirectory $WorkDir

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 31)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances Queue `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Mana Guruji staging terraform apply (A1 capacity retry)" `
        -Force | Out-Null
} catch {
    Write-Error "Register-ScheduledTask failed: $($_.Exception.Message)"
    exit 1
}

$info = Get-ScheduledTask -TaskName $TaskName
Write-Host "OK - scheduled task registered: $TaskName"
Write-Host "Every $IntervalMinutes minute(s) for 31 days (re-register monthly if still waiting on A1)."
Write-Host "Script: $ScriptPath"
Write-Host "Logs:   $WorkDir\..\terraform\environments\staging\retry-apply.log"
Write-Host "        $WorkDir\task-run.log (bootstrap if staging log empty)"
Write-Host "Test:   schtasks /Run /TN $TaskName"
Write-Host ('Remove: Unregister-ScheduledTask -TaskName ' + $TaskName + ' -Confirm:$false')
