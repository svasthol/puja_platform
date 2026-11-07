#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Print copy-paste commands to tee API, Celery, Beat, Admin UI, and Flutter logs into puja_platform/logs/.
.DESCRIPTION
  Does not start services unless -StartApi is used (optional). Creates logs/ if missing.
#>
param(
    [switch]$StartApi
)

$ErrorActionPreference = "Stop"
# Script lives in puja_platform/scripts/
$Root = Split-Path $PSScriptRoot -Parent
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

Write-Host "Log directory: $Logs" -ForegroundColor Cyan
Write-Host ""
Write-Host "=== Run each in its own terminal (from puja_platform unless noted) ===" -ForegroundColor Yellow
Write-Host @"

# API (Windows + reload — match dev habit)
python -c "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=True)" *>&1 | Tee-Object -FilePath logs/api.log -Append

# E2E UI
python tests/e2e_ui/serve.py *>&1 | Tee-Object -FilePath logs/e2e-ui.log -Append

# Celery worker (your queue + solo pool)
celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications --pool=solo *>&1 | Tee-Object -FilePath logs/celery-workers.log -Append

# Celery beat
celery -A app.workers.celery_app beat --loglevel=info *>&1 | Tee-Object -FilePath logs/beat.log -Append

# Admin UI (run from admin_ui/)
cd admin_ui; npm run dev *>&1 | Tee-Object -FilePath ../logs/adminui.log -Append

# Flutter customer (run from sibling folder mana_guruji_mobile/)
# Log path: ../puja_platform/logs/ relative to mana_guruji_mobile
flutter run --flavor customer -t lib/main_customer.dart --dart-define=API_BASE_URL=http://127.0.0.1:8000 -v *>&1 | Tee-Object -FilePath ../puja_platform/logs/customer.log -Append

# Flutter partner
flutter run --flavor partner -t lib/main_partner.dart --dart-define=API_BASE_URL=http://127.0.0.1:8000 -v *>&1 | Tee-Object -FilePath ../puja_platform/logs/partner.log -Append

# Redis MONITOR (dev only — noisy)
# redis-cli MONITOR *>&1 | Tee-Object -FilePath logs/redis.log -Append
"@

if ($StartApi) {
    Write-Host "Starting API with log tee (Ctrl+C to stop)..." -ForegroundColor Green
    Set-Location $Root
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 *>&1 | Tee-Object -FilePath (Join-Path $Logs "api.log") -Append
}
