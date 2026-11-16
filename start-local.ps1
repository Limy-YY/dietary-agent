# start-local.ps1
# One-click local full-stack startup:
#   [1] ensure DB container (diet-agent-db) is up + healthy
#   [2] create diet_backend login account (diet_app group is NOLOGIN, cannot log in)
#   [3] start backend :8000   (app.main:app)
#   [4] start agent   :8001   (main:app)
#
# Usage (PowerShell, any directory):
#   powershell -NoProfile -ExecutionPolicy Bypass -File start-local.ps1
#   (or double-click start-local.bat)
#
# ASCII-only on purpose: PowerShell 5.1 misreads UTF-8 (no BOM) Chinese text.

$ErrorActionPreference = 'Stop'

$repoRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$dockerDir  = Join-Path $repoRoot 'docker'
$backendDir = Join-Path $repoRoot 'backend'
$agentDir   = Join-Path $repoRoot 'agent'
$venvPy     = Join-Path $repoRoot '.venv\Scripts\python.exe'

function Step([string]$n, [string]$msg) { Write-Host "`n== [$n] $msg ==" -ForegroundColor Cyan }

function Test-PortListening([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

# ---------- [1] DB ----------
Step '1' 'Ensure DB container is running + healthy'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: docker not found. Install / start Docker Desktop first.' -ForegroundColor Red
    exit 1
}
$running = docker ps --filter 'name=diet-agent-db' --format '{{.Names}}' 2>$null
if ($running -notmatch 'diet-agent-db') {
    Write-Host 'DB container not running -> docker compose up -d --build (first build may take minutes)...'
    Push-Location $dockerDir
    docker compose up -d --build
    Pop-Location
}
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    $st = docker inspect --format '{{.State.Health.Status}}' diet-agent-db 2>$null
    if ($st -eq 'healthy') { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    Write-Host 'ERROR: DB not healthy after 120s. Check: docker compose -f docker/docker-compose.yml logs db' -ForegroundColor Red
    exit 1
}
Write-Host 'DB healthy.' -ForegroundColor Green

# ---------- [2] login account ----------
Step '2' 'Create diet_backend login account (grant_backend_login.sql)'
$grant = Join-Path $backendDir 'scripts\grant_backend_login.sql'
docker cp $grant diet-agent-db:/tmp/grant_backend_login.sql
docker exec diet-agent-db psql -U postgres -d diet_agent -f /tmp/grant_backend_login.sql

# ---------- [3] backend ----------
Step '3' 'Start backend :8000'
if (Test-PortListening 8000) {
    Write-Host 'backend already listening on 8000, skip.' -ForegroundColor Yellow
} else {
    Start-Process -FilePath $venvPy -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000' -WorkingDirectory $backendDir
    Write-Host 'backend window opened.' -ForegroundColor Green
}

# ---------- [4] agent ----------
Step '4' 'Start agent :8001'
if (Test-PortListening 8001) {
    Write-Host 'agent already listening on 8001, skip.' -ForegroundColor Yellow
} else {
    Start-Process -FilePath $venvPy -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $agentDir
    Write-Host 'agent window opened.' -ForegroundColor Green
}

Write-Host "`nAll done. Verify:" -ForegroundColor Green
Write-Host '  backend : http://127.0.0.1:8000/api/health   (expect status=ok database=ok)'
Write-Host '  agent   : http://127.0.0.1:8001/health        (expect llm=true)'
Write-Host '  frontend: cd frontend; npm run dev  (set VITE_USE_MOCK=false in frontend/.env.development)'
