# Dev laptop: SSH tunnel (15432) → compare local Postgres vs staging → optional safe migrate.
# Staging Postgres is 127.0.0.1:5432 on VM — not public :5432.
param(
    [switch]$UpdateIngress,
    [switch]$EnsureTunnel,
    [switch]$Compare,
    [switch]$Strict,
    [ValidateSet("none", "plan", "staging-migrate")]
    [string]$Sync = "none",
    [switch]$Yes,
    [string]$DevUrl = $env:DEV_DATABASE_URL,
    [string]$StagingUrl = $env:STAGING_DATABASE_URL
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Push-Location $RepoRoot
try {
    $py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py", "-3" }
    $args = @("scripts/db_dev_staging_parity.py")
    if ($UpdateIngress) { $args += "--update-ingress" }
    if ($EnsureTunnel) { $args += "--ensure-tunnel" }
    if ($Compare) { $args += "--compare" }
    if ($Strict) { $args += "--strict" }
    if ($Sync -ne "none") { $args += "--sync", $Sync }
    if ($Yes) { $args += "--yes" }
    if ($DevUrl) { $args += "--dev-url", $DevUrl }
    if ($StagingUrl) { $args += "--staging-url", $StagingUrl }

    & $py @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
