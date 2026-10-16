# Single terraform apply for staging (Scheduled Task or manual). Exits 0 on success.
$ErrorActionPreference = "Continue"

$ScriptRoot = $PSScriptRoot
$StagingDir = [System.IO.Path]::GetFullPath((Join-Path $ScriptRoot "..\terraform\environments\staging"))
$LogFile = Join-Path $StagingDir "retry-apply.log"
$BootstrapLog = Join-Path $ScriptRoot "task-run.log"

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    foreach ($path in @($LogFile, $BootstrapLog)) {
        try {
            Add-Content -LiteralPath $path -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
        } catch { }
    }
}

Write-Log "TASK START user=$env:USERNAME pid=$PID cwd=$(Get-Location)"

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [Environment]::GetEnvironmentVariable("Path", "User")

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptRoot "..\..\.."))
$ociConfig = Join-Path $RepoRoot ".oci\config"
if (-not (Test-Path -LiteralPath $ociConfig)) {
    Write-Log "ERROR - missing .oci/config under puja_platform"
    exit 1
}

try {
    . (Join-Path $ScriptRoot "Set-OciConfig.ps1")
} catch {
    Write-Log "ERROR - Set-OciConfig.ps1 failed: $($_.Exception.Message)"
    exit 1
}
Write-Log "OCI TF_VAR auth loaded"

function Resolve-TerraformCommand {
    $cmd = Get-Command terraform -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $found = Get-ChildItem -Path $wingetRoot -Filter "terraform.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $classic = "${env:ProgramFiles}\Terraform\terraform.exe"
    if (Test-Path -LiteralPath $classic) { return $classic }
    return $null
}

$Terraform = Resolve-TerraformCommand
if (-not $Terraform) {
    Write-Log "ERROR - terraform.exe not found. Add Terraform to User PATH and re-register task."
    exit 127
}

if (-not (Test-Path -LiteralPath $StagingDir)) {
    Write-Log "ERROR - staging dir missing: $StagingDir"
    exit 1
}

Set-Location $StagingDir
Write-Log "terraform=$Terraform staging=$StagingDir"

$ApplyTimeoutMinutes = 20
$stdoutFile = Join-Path $env:TEMP ("mg-stg-tf-apply-{0}.stdout" -f $PID)
$stderrFile = Join-Path $env:TEMP ("mg-stg-tf-apply-{0}.stderr" -f $PID)
Remove-Item -LiteralPath $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath $Terraform `
    -ArgumentList @("apply", "-auto-approve", "-no-color") `
    -WorkingDirectory $StagingDir `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile `
    -NoNewWindow `
    -PassThru

$exitCode = 1
$timedOut = -not $proc.WaitForExit($ApplyTimeoutMinutes * 60 * 1000)
if ($timedOut) {
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    Write-Log "ERROR - terraform apply exceeded ${ApplyTimeoutMinutes}m; killed pid=$($proc.Id). OCI may have hung waiting on capacity."
    $exitCode = 124
} elseif ($null -ne $proc.ExitCode) {
    $exitCode = $proc.ExitCode
}

$out = @()
if (Test-Path -LiteralPath $stdoutFile) { $out += Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue }
if (Test-Path -LiteralPath $stderrFile) { $out += Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue }
$out = ($out | Where-Object { $_ }) -join "`n"
Add-Content -LiteralPath $LogFile -Value $out -Encoding utf8
Remove-Item -LiteralPath $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

if ($exitCode -eq 0) {
    Write-Log "SUCCESS - apply completed."
    & $Terraform output -no-color 2>&1 | ForEach-Object { Write-Log $_ }
    exit 0
}

if ($out -match "Out of host capacity") {
    Write-Log "No A1 capacity yet; next scheduled retry."
} elseif ($out -match "bootVolumeQuota|QuotaExceeded") {
    Write-Log "Quota error - fix in OCI Console."
}

Write-Log ("Apply failed with exit code {0}." -f $exitCode)
exit $exitCode
