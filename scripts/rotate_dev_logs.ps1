#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Move current puja_platform/logs/*.log into logs/archive/ with a timestamp (dev / E2E).
.DESCRIPTION
  Run once before starting services if you want a fresh log file without losing history.
  Does not touch archived files. Git ignores *.log and archive/* via .gitignore patterns for logs folder.
#>
param(
    [string[]]$Names = @(
        "api.log", "adminui.log", "e2e-ui.log",
        "celery-workers.log", "beat.log",
        "customer.log", "partner.log", "redis.log"
    )
)

$ErrorActionPreference = "Stop"
$PlatformRoot = Split-Path $PSScriptRoot -Parent
$LogsDir = Join-Path $PlatformRoot "logs"
$ArchiveDir = Join-Path $LogsDir "archive"
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$moved = 0

foreach ($name in $Names) {
    $path = Join-Path $LogsDir $name
    if (-not (Test-Path $path)) { continue }
    $base = [System.IO.Path]::GetFileNameWithoutExtension($name)
    $dest = Join-Path $ArchiveDir "${base}-${stamp}.log"
    Move-Item -LiteralPath $path -Destination $dest -Force
    Write-Host "Rotated: $name -> archive/$(Split-Path $dest -Leaf)" -ForegroundColor Green
    $moved++
}

if ($moved -eq 0) {
    Write-Host "No log files to rotate under $LogsDir (OK for first run)." -ForegroundColor DarkGray
}
