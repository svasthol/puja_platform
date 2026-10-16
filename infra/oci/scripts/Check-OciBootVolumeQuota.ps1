# Diagnose boot volume quota before terraform apply (writes NDJSON to workspace debug-9553cd.log).
param(
    [Parameter(Mandatory = $true)]
    [string]$CompartmentId
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$WorkspaceRoot = (Resolve-Path (Join-Path $RepoRoot "..\..")).Path
$DebugLog = Join-Path $WorkspaceRoot "debug-9553cd.log"

. (Join-Path $PSScriptRoot "Set-OciConfig.ps1")

function Write-DebugNdjson {
    param([string]$HypothesisId, [string]$Location, [string]$Message, [hashtable]$Data)
    # #region agent log
    $payload = @{
        sessionId    = "9553cd"
        hypothesisId = $HypothesisId
        location     = $Location
        message      = $Message
        data         = $Data
        timestamp    = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
        runId        = "quota-check"
    } | ConvertTo-Json -Compress
    Add-Content -LiteralPath $DebugLog -Value $payload -Encoding utf8
    # #endregion
}

Write-Host "Compartment: $CompartmentId"
Write-Host "Debug log: $DebugLog"

$bvJson = oci bv boot-volume list --compartment-id $CompartmentId --all 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-DebugNdjson "H1" "Check-OciBootVolumeQuota.ps1" "boot_volume_list_failed" @{ exitCode = $LASTEXITCODE }
    Write-Error $bvJson
}
$bv = $bvJson | ConvertFrom-Json
$items = @($bv.data)
$totalGb = 0
foreach ($v in $items) {
    $sz = $v.'size-in-gbs'
    if ($null -ne $sz) { $totalGb += [int]$sz }
}
Write-DebugNdjson "H1" "Check-OciBootVolumeQuota.ps1" "boot_volumes_in_compartment" @{
    count   = $items.Count
    totalGb = $totalGb
    states  = ($items | ForEach-Object { $_."lifecycle-state" } | Sort-Object -Unique) -join ","
}

$limitsJson = oci limits resource-availability get `
    --service-name compute `
    --limit-name boot-volume-count `
    --compartment-id $CompartmentId `
    --availability-domain (oci iam availability-domain list --query "data[0].name" --raw-output) 2>&1
if ($LASTEXITCODE -eq 0) {
    $lim = $limitsJson | ConvertFrom-Json
    Write-DebugNdjson "H2" "Check-OciBootVolumeQuota.ps1" "limit_boot_volume_count" @{
        available = $lim.data.available
        used      = $lim.data.used
        fractionalUsage = $lim.data."fractional-usage"
    }
}

$limitsGb = oci limits resource-availability get `
    --service-name block-storage `
    --limit-name total-storage-gb `
    --compartment-id $CompartmentId 2>&1
if ($LASTEXITCODE -eq 0) {
    $lg = $limitsGb | ConvertFrom-Json
    Write-DebugNdjson "H3" "Check-OciBootVolumeQuota.ps1" "limit_total_storage_gb" @{
        available = $lg.data.available
        used      = $lg.data.used
    }
}

Write-Host "Boot volumes: $($items.Count) (sum ~${totalGb} GB). See $DebugLog for details."
Write-Host "If quota exceeded: delete unused boot volumes in Console (Block Storage). Keep boot_volume_gb at 50 (OL9 minimum), then terraform apply again."
