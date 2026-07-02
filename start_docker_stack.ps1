# BhajanForge — one-click Docker bring-up (run AFTER a reboot).
# Starts Docker Desktop, waits for the engine, then launches the stack.
# Usage:  right-click -> "Run with PowerShell"   (or)   pwsh ./start_docker_stack.ps1

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$dockerCli = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"

Write-Host "==> BhajanForge Docker bring-up" -ForegroundColor Cyan

# 1. Make sure the docker CLI is on PATH for this session.
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

# 2. Start Docker Desktop if it isn't already running.
if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process $dockerExe
} else {
    Write-Host "Docker Desktop already running." -ForegroundColor Green
}

# 3. Wait (up to 5 min) for the Docker engine to accept connections.
Write-Host "Waiting for the Docker engine to start (can take a few minutes on first run)..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        & $dockerCli info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 5
    Write-Host ("  ...still waiting ({0}s)" -f (($i + 1) * 5))
}

if (-not $ready) {
    Write-Host "Docker engine did not come up. Open Docker Desktop manually and wait for 'Engine running', then re-run this script." -ForegroundColor Red
    exit 1
}
Write-Host "Docker engine is running." -ForegroundColor Green

# 4. Smoke test.
Write-Host "==> docker run hello-world"
& $dockerCli run --rm hello-world

# 5. Bring up the BhajanForge stack (Qdrant + MCP servers + API).
Write-Host "==> docker compose up -d (building images; first run is slow)" -ForegroundColor Cyan
Push-Location $repo
try {
    & $dockerCli compose up -d --build
    Write-Host "==> Containers:" -ForegroundColor Cyan
    & $dockerCli compose ps
} finally {
    Pop-Location
}

# 6. Health check the API.
Write-Host "==> Checking API health at http://localhost:8000/healthz"
Start-Sleep -Seconds 5
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:8000/healthz" -TimeoutSec 15
    Write-Host ("API healthy: {0}" -f ($resp | ConvertTo-Json -Compress)) -ForegroundColor Green
} catch {
    Write-Host "API not responding yet; give it a moment and check 'docker compose logs api'." -ForegroundColor Yellow
}

Write-Host "==> Done. Stop the stack later with:  docker compose down" -ForegroundColor Cyan
