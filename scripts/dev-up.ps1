# JARVIS local development bring-up (Windows / PowerShell).
#
#   .\scripts\dev-up.ps1            # start postgres, then healthcheck
#   .\scripts\dev-up.ps1 -Down      # stop the stack (data volume preserved)
#   .\scripts\dev-up.ps1 -Reset     # stop AND delete the data volume
#
# Backend and frontend run natively on the host; only infrastructure is
# containerized. See ADR-002.

param(
    [switch]$Down,
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }

if ($Reset) {
    Write-Step "Tearing down stack and deleting the postgres volume"
    docker compose down -v
    exit $LASTEXITCODE
}

if ($Down) {
    Write-Step "Stopping stack (data volume preserved)"
    docker compose down
    exit $LASTEXITCODE
}

Write-Step "Checking the Docker daemon"
docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if (-not $?) {
    Write-Warn "Docker daemon is not responding. Start Docker Desktop and re-run."
    exit 1
}

if (-not (Test-Path "$RepoRoot\.env")) {
    Write-Step "Creating .env from .env.example"
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
}

Write-Step "Starting PostgreSQL (pgvector)"
docker compose up -d postgres
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Waiting for PostgreSQL to report healthy"
$deadline = (Get-Date).AddSeconds(90)
do {
    $state = docker inspect --format '{{.State.Health.Status}}' jarvis-postgres 2>$null
    if ($state -eq "healthy") { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if ($state -ne "healthy") {
    Write-Warn "PostgreSQL did not become healthy in time. Check: docker compose logs postgres"
    exit 1
}
Write-Host "    postgres: healthy" -ForegroundColor Green

Write-Step "Running the environment healthcheck"
python "$RepoRoot\scripts\healthcheck.py"
exit $LASTEXITCODE
