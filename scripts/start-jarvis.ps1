# Start everything the console needs, each in its own window:
#   Docker (Postgres + Neo4j), the API on :8000, the web console on :5173, then open the browser.
#
#     powershell -ExecutionPolicy Bypass -File scripts\start-jarvis.ps1
#
# Ollama runs natively (ADR-003) and starts with Windows; this checks it is answering.
# Close the two windows to stop the API and the console; `docker compose stop` stops the databases.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Docker: Postgres and Neo4j"
docker compose up -d postgres neo4j
if ($LASTEXITCODE -ne 0) { Write-Host "Docker is not running. Start Docker Desktop and run this again." -ForegroundColor Yellow; exit 1 }

Step "Ollama"
try { Invoke-RestMethod http://localhost:11434/api/tags -TimeoutSec 3 | Out-Null; Write-Host "    answering" }
catch { Write-Host "    not answering - start Ollama from the Start menu; investigations need it" -ForegroundColor Yellow }

Step "API on http://localhost:8000"
$python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\backend'; & '$python' -m uvicorn app.api.app:create_app --factory --port 8000"

Step "Web console on http://localhost:5173"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"

Step "Waiting for the API"
$deadline = (Get-Date).AddSeconds(60)
do {
    try { Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2 | Out-Null; $up = $true } catch { $up = $false; Start-Sleep 2 }
} until ($up -or (Get-Date) -gt $deadline)
if ($up) { Write-Host "    ready" } else { Write-Host "    not up yet - check the API window" -ForegroundColor Yellow }

Start-Process "http://localhost:5173"
