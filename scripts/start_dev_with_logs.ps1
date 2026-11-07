#!/usr/bin/env pwsh
#requires -Version 5.1
<#
.SYNOPSIS
  Open minimized windows for local dev; tee stdout/stderr into puja_platform/logs/*.log
.DESCRIPTION
  Run from puja_platform/. Uses .venv\Scripts\python.exe and celery.exe when present.
  By default skips a service if its port (or Celery process) looks already running — prints CLEAR message.
  Use -Force to attempt start anyway. Use -SkipPreflight to disable checks.

.EXAMPLE
  .\scripts\start_dev_with_logs.ps1 -RotateFirst
.EXAMPLE
  .\scripts\start_dev_with_logs.ps1 -Force
#>
param(
    [switch]$RotateFirst,
    [switch]$SkipApi,
    [switch]$SkipAdmin,
    [switch]$SkipWorker,
    [switch]$SkipBeat,
    [switch]$SkipE2E,
    [switch]$SkipFlutterCustomer,
    [switch]$SkipFlutterPartner,
    [switch]$Force,
    [switch]$SkipPreflight,
    [int]$ApiPort = 8000,
    [int]$AdminPort = 3000,
    [int]$E2EPort = 8765,
    [string]$FlutterApiUrl = "http://127.0.0.1:8000",
    [string]$MobileRoot = ""
)

$ErrorActionPreference = "Stop"
$PlatformRoot = Split-Path $PSScriptRoot -Parent
$LogsDir = Join-Path $PlatformRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Test-TcpPortOpen {
    param([string]$HostName = '127.0.0.1', [int]$Port, [int]$TimeoutMs = 400)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $connect = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($connect)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Get-CeleryProcs {
    param([string]$Role)
    try {
        Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $cmd = $_.CommandLine
                if (-not $cmd) { return $false }
                if ($cmd -notlike '*celery*') { return $false }
                if ($cmd -notlike '*app.workers.celery_app*') { return $false }
                if ($Role -eq 'worker') {
                    return ($cmd -match 'celery(\.exe)?\s+.*\bworker\b')
                }
                if ($Role -eq 'beat') {
                    return ($cmd -match 'celery(\.exe)?\s+.*\bbeat\b')
                }
                return $false
            }
    } catch {
        @()
    }
}

function Test-CeleryAlreadyRunning {
    param([string]$Role)
    $p = @(Get-CeleryProcs -Role $Role)
    return ($p.Count -gt 0)
}

function Write-SkipRunning {
    param([string]$Name, [string]$Reason)
    Write-Host "[SKIP] $Name — already running ($Reason). Use -Force to start another instance anyway." -ForegroundColor Yellow
}

$doFlutterCustomer = -not $SkipFlutterCustomer
$doFlutterPartner = -not $SkipFlutterPartner

$resolvedMobile = $MobileRoot
if ([string]::IsNullOrWhiteSpace($resolvedMobile)) {
    $defaultMobile = Join-Path $PlatformRoot "..\mana_guruji_mobile"
    if (Test-Path -LiteralPath $defaultMobile) {
        $resolvedMobile = (Resolve-Path -LiteralPath $defaultMobile).Path
    } else {
        $resolvedMobile = $null
        if ($doFlutterCustomer -or $doFlutterPartner) {
            Write-Host "mana_guruji_mobile not found next to puja_platform — use -MobileRoot or -SkipFlutter*" -ForegroundColor Yellow
        }
        $doFlutterCustomer = $false
        $doFlutterPartner = $false
    }
} elseif (-not (Test-Path -LiteralPath $resolvedMobile)) {
    Write-Host "Invalid -MobileRoot: $resolvedMobile" -ForegroundColor Red
    exit 1
}

function Get-VenvPython {
    $p = Join-Path $PlatformRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $p) { return $p }
    return "python"
}

function Get-VenvCelery {
    $p = Join-Path $PlatformRoot ".venv\Scripts\celery.exe"
    if (Test-Path -LiteralPath $p) { return $p }
    return "celery"
}

$py = Get-VenvPython
$celeryExe = Get-VenvCelery
$platEsc = $PlatformRoot.Replace("'", "''")
$pyEsc = $py.Replace("'", "''")
$celEsc = $celeryExe.Replace("'", "''")

if ($RotateFirst) {
    $rot = Join-Path $PlatformRoot "scripts\rotate_dev_logs.ps1"
    if (Test-Path $rot) {
        Write-Host "Rotating logs..." -ForegroundColor Cyan
        & $rot
    }
}

function Start-LoggedWindow {
    param(
        [string]$Title,
        [string]$Command,
        [string]$WorkDir
    )
    $exe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    $p = Start-Process -FilePath $exe -WorkingDirectory $WorkDir `
        -ArgumentList "-NoExit", "-Command", $Command `
        -WindowStyle Minimized -PassThru
    Write-Host "[OK] Started: $Title (PID $($p.Id))" -ForegroundColor Green
}

$apiCmdLine = "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=$ApiPort, reload=True)"

# --- API ---
if (-not $SkipApi) {
    $skip = $false
    if (-not $SkipPreflight -and -not $Force) {
        if (Test-TcpPortOpen -Port $ApiPort) {
            Write-SkipRunning "API" "something is listening on 127.0.0.1:$ApiPort"
            $skip = $true
        }
    }
    if (-not $skip) {
        $apiCmd = @"
`$ErrorActionPreference = 'Continue'
`$env:PYTHONUNBUFFERED = '1'
Set-Location -LiteralPath '$platEsc'
New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
if (Test-Path -LiteralPath '.venv\Scripts\Activate.ps1') { . '.venv\Scripts\Activate.ps1' }
& '$pyEsc' -c "$apiCmdLine" *>&1 | Tee-Object -FilePath 'logs/api.log' -Append
"@
        Start-LoggedWindow "API" $apiCmd $PlatformRoot
    }
}

# --- Celery worker ---
if (-not $SkipWorker) {
    $skip = $false
    if (-not $SkipPreflight -and -not $Force) {
        if (Test-CeleryAlreadyRunning -Role 'worker') {
            Write-SkipRunning "Celery worker" "detected existing celery worker process for this app"
            $skip = $true
        }
    }
    if (-not $skip) {
        $wCmd = @"
`$ErrorActionPreference = 'Continue'
`$env:PYTHONUNBUFFERED = '1'
Set-Location -LiteralPath '$platEsc'
New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
if (Test-Path -LiteralPath '.venv\Scripts\Activate.ps1') { . '.venv\Scripts\Activate.ps1' }
& '$celEsc' -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications --pool=solo *>&1 | Tee-Object -FilePath 'logs/celery-workers.log' -Append
"@
        Start-LoggedWindow "Celery worker" $wCmd $PlatformRoot
    }
}

# --- Celery beat ---
if (-not $SkipBeat) {
    $skip = $false
    if (-not $SkipPreflight -and -not $Force) {
        if (Test-CeleryAlreadyRunning -Role 'beat') {
            Write-SkipRunning "Celery beat" "detected existing celery beat process for this app"
            $skip = $true
        }
    }
    if (-not $skip) {
        $bCmd = @"
`$ErrorActionPreference = 'Continue'
`$env:PYTHONUNBUFFERED = '1'
Set-Location -LiteralPath '$platEsc'
New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
if (Test-Path -LiteralPath '.venv\Scripts\Activate.ps1') { . '.venv\Scripts\Activate.ps1' }
& '$celEsc' -A app.workers.celery_app beat --loglevel=info *>&1 | Tee-Object -FilePath 'logs/beat.log' -Append
"@
        Start-LoggedWindow "Celery beat" $bCmd $PlatformRoot
    }
}

# --- E2E UI ---
if (-not $SkipE2E) {
    $skip = $false
    if (-not $SkipPreflight -and -not $Force) {
        if (Test-TcpPortOpen -Port $E2EPort) {
            Write-SkipRunning "E2E UI server" "something is listening on 127.0.0.1:$E2EPort (tests/e2e_ui/serve.py default)"
            $skip = $true
        }
    }
    if (-not $skip) {
        $eCmd = @"
`$ErrorActionPreference = 'Continue'
`$env:PYTHONUNBUFFERED = '1'
Set-Location -LiteralPath '$platEsc'
New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
if (Test-Path -LiteralPath '.venv\Scripts\Activate.ps1') { . '.venv\Scripts\Activate.ps1' }
& '$pyEsc' tests/e2e_ui/serve.py *>&1 | Tee-Object -FilePath 'logs/e2e-ui.log' -Append
"@
        Start-LoggedWindow "E2E UI" $eCmd $PlatformRoot
    }
}

# --- Admin UI ---
if (-not $SkipAdmin) {
    $adminDir = Join-Path $PlatformRoot "admin_ui"
    if (-not (Test-Path $adminDir)) {
        Write-Host "[SKIP] Admin UI — admin_ui not found at $adminDir" -ForegroundColor Yellow
    } else {
        $skip = $false
        if (-not $SkipPreflight -and -not $Force) {
            if (Test-TcpPortOpen -Port $AdminPort) {
                Write-SkipRunning "Admin UI" "something is listening on 127.0.0.1:$AdminPort (next dev uses this by default)"
                $skip = $true
            }
        }
        if (-not $skip) {
            $adminEsc = $adminDir.Replace("'", "''")
            $aCmd = @"
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$adminEsc'
New-Item -ItemType Directory -Force -Path '../logs' | Out-Null
if (Get-Command npm.ps1 -ErrorAction SilentlyContinue) {
  & npm.ps1 run dev *>&1 | Tee-Object -FilePath '../logs/adminui.log' -Append
} else {
  npm run dev *>&1 | Tee-Object -FilePath '../logs/adminui.log' -Append
}
"@
            Start-LoggedWindow "Admin UI" $aCmd $adminDir
        }
    }
}

# --- Flutter (no reliable "already running" check — document in README) ---
function Start-FlutterLogged {
    param([string]$Flavor, [string]$Entry, [string]$LogName)
    if ([string]::IsNullOrEmpty($resolvedMobile)) { return }
    $mobEsc = $resolvedMobile.Replace("'", "''")
    $logAbs = (Join-Path $LogsDir $LogName).Replace("'", "''")
    $defEsc = $FlutterApiUrl.Replace("'", "''")
    if (-not $SkipPreflight -and -not $Force) {
        $skipHint = if ($Flavor -eq 'customer') { '-SkipFlutterCustomer' } else { '-SkipFlutterPartner' }
        Write-Host "[INFO] Flutter $Flavor — duplicate run is not auto-detected; use $skipHint if already running." -ForegroundColor DarkGray
    }
    $fCmd = @"
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$mobEsc'
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
  Write-Host 'flutter not on PATH' -ForegroundColor Red
  pause
  exit 1
}
flutter run --flavor $Flavor -t $Entry --dart-define=API_BASE_URL=$defEsc -v *>&1 | Tee-Object -FilePath '$logAbs' -Append
"@
    Start-LoggedWindow "Flutter $Flavor" $fCmd $resolvedMobile
}

if ($doFlutterCustomer) {
    Start-FlutterLogged "customer" "lib/main_customer.dart" "customer.log"
}
if ($doFlutterPartner) {
    Start-FlutterLogged "partner" "lib/main_partner.dart" "partner.log"
}

Write-Host ""
Write-Host "Logs: $LogsDir" -ForegroundColor Cyan
Write-Host "watch: pwsh -File scripts/watch_e2e_logs.ps1 -Once" -ForegroundColor DarkGray
Write-Host "Preflight: ports API=$ApiPort admin=$AdminPort e2e=$E2EPort  |  -Force bypasses  |  -SkipPreflight disables checks" -ForegroundColor DarkGray
