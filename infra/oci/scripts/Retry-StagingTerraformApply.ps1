# Retry terraform apply for staging until stg-aio-1 is created (A1 capacity waiter).
# Run ONE copy only. Uses Enable-PreventSystemSleep so PC does not sleep during the loop.
# If the PC still sleeps (lid closed / hibernate), use Register-StagingTerraformRetryTask.ps1 instead.
param(
    [int]$IntervalMinutes = 10,
    [int]$MaxAttempts = 0  # 0 = unlimited until success or Ctrl+C
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "Enable-PreventSleepWhileRetry.ps1")
. (Join-Path $PSScriptRoot "Set-OciConfig.ps1")

Enable-PreventSystemSleep
try {

$StagingDir = Join-Path $PSScriptRoot "..\terraform\environments\staging"
$StagingDir = (Resolve-Path $StagingDir).Path
$LogFile = Join-Path $StagingDir "retry-apply.log"

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8
}

Set-Location $StagingDir
Write-Log "Retry-StagingTerraformApply started. Interval=${IntervalMinutes}m MaxAttempts=$MaxAttempts"
Write-Log "Working directory: $StagingDir"

$attempt = 0
while ($true) {
    $attempt++
    if ($MaxAttempts -gt 0 -and $attempt -gt $MaxAttempts) {
        Write-Log "MaxAttempts reached ($MaxAttempts). Stopping."
        exit 1
    }

    Write-Log "Attempt $attempt — terraform apply -auto-approve"
    $out = terraform apply -auto-approve -no-color 2>&1 | Out-String
    Add-Content -LiteralPath $LogFile -Value $out -Encoding utf8

    if ($LASTEXITCODE -eq 0) {
        Write-Log "SUCCESS — terraform apply completed."
        terraform output -no-color 2>&1 | ForEach-Object { Write-Log $_ }
        exit 0
    }

    if ($out -match "Out of host capacity") {
        Write-Log "Still no A1 host capacity. Sleeping ${IntervalMinutes} minute(s)..."
    } elseif ($out -match "bootVolumeQuota|QuotaExceeded") {
        Write-Log "Quota error — fix in Console before retrying. Stopping loop."
        exit 2
    } else {
        Write-Log "Apply failed (exit $LASTEXITCODE). Sleeping ${IntervalMinutes} minute(s) before retry..."
    }

    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
}
finally {
    Disable-PreventSystemSleep
}
