# TEST ONLY — restart E2E UI server (kills stale listeners on 8765).
$ErrorActionPreference = "Stop"
$Port = if ($env:E2E_UI_PORT) { [int]$env:E2E_UI_PORT } else { 8765 }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $Root)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Write-Host "Stopping processes listening on port $Port..."
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Set-Location $Root
Write-Host "Starting serve.py (E2E UI v2 with Test ops)..."
& $Python serve.py
