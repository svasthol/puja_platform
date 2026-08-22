# Start FastAPI for physical-device testing (LAN + Windows selector loop).
# Usage: from puja_platform with venv active:
#   .\tool\run_api_lan.ps1

$ErrorActionPreference = "Stop"
$port = 8000

$ip = (
    Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.PrefixOrigin -ne "WellKnown"
    } |
    Sort-Object InterfaceMetric |
    Select-Object -First 1
).IPAddress

Write-Host "LAN API will listen on 0.0.0.0:$port"
if ($ip) {
    Write-Host "Phone API_BASE_URL: http://${ip}:$port"
    Write-Host "Phone health check: http://${ip}:$port/health/live"
}

# Allow inbound on port (idempotent; needs admin once).
$ruleName = "ManaGuruji API $port"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    Write-Host "Tip: if phone cannot connect, run as Admin:"
    Write-Host "  New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port"
}

python -c @"
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uvicorn
uvicorn.run('app.main:app', host='0.0.0.0', port=$port, reload=True)
"@
