# restart-local.ps1
# One-click RESTART of backend (:8000) and agent (:8001).
#   [1] auto-find & kill whatever process listens on 8000 / 8001
#   [2] start backend   :8000  (app.main:app)
#   [3] start agent     :8001  (main:app)
# DB is NOT touched here (assumed still running).
#
# Usage (PowerShell, any directory):
#   powershell -NoProfile -ExecutionPolicy Bypass -File restart-local.ps1
#   (or double-click restart-local.bat)
#
# ASCII-only on purpose: PowerShell 5.1 misreads UTF-8 (no BOM) Chinese text.

$ErrorActionPreference = 'Stop'

$repoRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot 'backend'
$agentDir   = Join-Path $repoRoot 'agent'
$venvPy     = Join-Path $repoRoot '.venv\Scripts\python.exe'

function Step([string]$n, [string]$msg) { Write-Host "`n== [$n] $msg ==" -ForegroundColor Cyan }

function Stop-Port([int]$port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "  port $port : nothing listening (already stopped)" -ForegroundColor Yellow
        return
    }
    # one port may have several PIDs (IPv4 + IPv6); dedupe and kill each.
    $pids = $conns.OwningProcess | Sort-Object -Unique
    foreach ($procId in $pids) {
        Write-Host "  port $port : killing PID $procId ..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 800
}

# ---------- [1] stop old backend / agent ----------
Step '1' 'Stop old backend(:8000) and agent(:8001) if running'
Stop-Port 8000
Stop-Port 8001

# ---------- [2] start backend ----------
Step '2' 'Start backend :8000'
Start-Process -FilePath $venvPy -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000' -WorkingDirectory $backendDir
Write-Host '  backend window opened.' -ForegroundColor Green

# ---------- [3] start agent ----------
Step '3' 'Start agent :8001'
Start-Process -FilePath $venvPy -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $agentDir
Write-Host '  agent window opened.' -ForegroundColor Green

Write-Host "`nRestarted. Verify (a few seconds for startup):" -ForegroundColor Green
Write-Host '  backend : http://127.0.0.1:8000/api/health   (expect status=ok database=ok)'
Write-Host '  agent   : http://127.0.0.1:8001/health        (expect llm=true)'
