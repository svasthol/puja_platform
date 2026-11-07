#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Scan puja_platform/logs/*.log for errors and high-signal patterns (E2E / Slice B).
.PARAMETER IntervalMinutes
  If > 0, re-run the scan every N minutes until Ctrl+C.
.PARAMETER Once
  Run a single scan and exit (good for Cursor Task on a schedule).
#>
param(
    [int]$IntervalMinutes = 0,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$PlatformRoot = Split-Path $PSScriptRoot -Parent
$LogsDir = Join-Path $PlatformRoot "logs"
if (-not (Test-Path $LogsDir)) {
    Write-Host "No logs directory yet: $LogsDir — create it or run services with tee (logs/README.md)" -ForegroundColor Yellow
    exit 0
}

$patterns = @(
    @{ Name = "ERROR|Error:"; Regex = '\b(ERROR|Traceback|Exception|CRITICAL|Fatal)\b' }
    @{ Name = "HTTP 4xx"; Regex = '\b4[0-9]{2}\b' }
    @{ Name = "HTTP 5xx"; Regex = '\b5[0-9]{2}\b' }
    @{ Name = "DioException"; Regex = 'DioException' }
    @{ Name = "redis|Redis down"; Regex = '(Redis|redis|Connection refused.*6379)' }
)

function Invoke-LogScan {
    $files = Get-ChildItem -Path $LogsDir -Filter "*.log" -File -ErrorAction SilentlyContinue
    if (-not $files) {
        Write-Host "[$(Get-Date -Format o)] No *.log files in $LogsDir" -ForegroundColor DarkGray
        return
    }
    Write-Host "`n========== E2E log scan $(Get-Date -Format o) ==========" -ForegroundColor Cyan
    foreach ($f in $Files) {
        Write-Host "--- $($f.Name) ($([math]::Round($f.Length/1KB,1)) KB) ---" -ForegroundColor DarkCyan
        $tail = Get-Content -Path $f.FullName -Tail 400 -ErrorAction SilentlyContinue
        if (-not $tail) { Write-Host "  (empty)" -ForegroundColor DarkGray; continue }
        $text = $tail -join "`n"
        $hits = 0
        foreach ($p in $patterns) {
            $m = [regex]::Matches($text, $p.Regex, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($m.Count -gt 0) {
                Write-Host "  [$($p.Name)] count=$($m.Count)" -ForegroundColor Yellow
                $hits += $m.Count
            }
        }
        if ($hits -eq 0) {
            Write-Host "  No error-pattern hits in last 400 lines." -ForegroundColor DarkGreen
        }
    }
}

if ($Once -or $IntervalMinutes -le 0) {
    Invoke-LogScan
    exit 0
}

Write-Host "Watching every $IntervalMinutes minute(s). Ctrl+C to stop." -ForegroundColor Green
while ($true) {
    Invoke-LogScan
    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
