# Diagnose boot volume quota before terraform apply.
param(
    [Parameter(Mandatory = $true)]
    [string]$CompartmentId
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Set-OciConfig.ps1")

Write-Host "Compartment: $CompartmentId"

$bvJson = oci bv boot-volume list --compartment-id $CompartmentId --all 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error $bvJson
}
$bv = $bvJson | ConvertFrom-Json
$items = @($bv.data)
$totalGb = 0
foreach ($v in $items) {
    $sz = $v.'size-in-gbs'
    if ($null -ne $sz) { $totalGb += [int]$sz }
}
$states = ($items | ForEach-Object { $_."lifecycle-state" } | Sort-Object -Unique) -join ", "
Write-Host "Boot volumes: $($items.Count) (sum ~${totalGb} GB). States: $states"

$limitsJson = oci limits resource-availability get `
    --service-name compute `
    --limit-name boot-volume-count `
    --compartment-id $CompartmentId `
    --availability-domain (oci iam availability-domain list --query "data[0].name" --raw-output) 2>&1
if ($LASTEXITCODE -eq 0) {
    $lim = $limitsJson | ConvertFrom-Json
    Write-Host ("boot-volume-count: used={0} available={1}" -f $lim.data.used, $lim.data.available)
}

$limitsGb = oci limits resource-availability get `
    --service-name block-storage `
    --limit-name total-storage-gb `
    --compartment-id $CompartmentId 2>&1
if ($LASTEXITCODE -eq 0) {
    $lg = $limitsGb | ConvertFrom-Json
    Write-Host ("total-storage-gb: used={0} available={1}" -f $lg.data.used, $lg.data.available)
}

Write-Host "If quota exceeded: delete unused boot volumes in Console (Block Storage). Keep boot_volume_gb at 50 (OL9 minimum), then terraform apply again."
