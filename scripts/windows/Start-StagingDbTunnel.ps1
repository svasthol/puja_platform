# Forward laptop 127.0.0.1:15432 -> stg-aio-1 127.0.0.1:5432 (Postgres not on public IP).
param(
    [string]$SshTarget = $(if ($env:STAGING_SSH) { $env:STAGING_SSH } else { "opc@140.245.245.201" }),
    [int]$LocalPort = $(if ($env:STAGING_DB_TUNNEL_PORT) { [int]$env:STAGING_DB_TUNNEL_PORT } else { 15432 })
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $RepoRoot
try {
    python scripts/staging_db_tunnel.py --ssh $SshTarget --local-port $LocalPort
}
finally {
    Pop-Location
}
