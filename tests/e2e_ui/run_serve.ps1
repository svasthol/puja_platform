# TEST ONLY - restart E2E UI server (kills stale listeners on 8765).
$ErrorActionPreference = "Stop"
$Port = if ($env:E2E_UI_PORT) { [int]$env:E2E_UI_PORT } else { 8765 }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $Root)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Write-Host "Stopping processes listening on port $Port..."
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# Belt-and-suspenders: kill any other serve.py on this port
Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -match "e2e_ui[\\/]serve\.py") {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
Start-Sleep -Seconds 1

Set-Location $Root
Write-Host "Starting serve.py (E2E UI v19 - Setu PAN Partner walkthrough)..."
Write-Host "Verify after start: http://127.0.0.1:$Port/e2e-ui-version.json should show version 17"
& $Python serve.py
