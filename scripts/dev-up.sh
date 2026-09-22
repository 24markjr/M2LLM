#!/usr/bin/env bash
# JARVIS local development bring-up (Linux / macOS / Git Bash).
#
#   ./scripts/dev-up.sh          # start postgres, then healthcheck
#   ./scripts/dev-up.sh --down   # stop the stack (data volume preserved)
#   ./scripts/dev-up.sh --reset  # stop AND delete the data volume
#
# Backend and frontend run natively on the host; only infrastructure is
# containerized. See ADR-002.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

step() { printf '\n==> %s\n' "$1"; }
warn() { printf '    ! %s\n' "$1" >&2; }

case "${1:-}" in
  --reset)
    step "Tearing down stack and deleting the postgres volume"
    exec docker compose down -v
    ;;
  --down)
    step "Stopping stack (data volume preserved)"
    exec docker compose down
    ;;
esac

step "Checking the Docker daemon"
if ! docker info >/dev/null 2>&1; then
  warn "Docker daemon is not responding. Start Docker and re-run."
  exit 1
fi

if [[ ! -f .env ]]; then
  step "Creating .env from .env.example"
  cp .env.example .env
fi

step "Starting PostgreSQL (pgvector)"
docker compose up -d postgres

step "Waiting for PostgreSQL to report healthy"
deadline=$(( SECONDS + 90 ))
state=""
while (( SECONDS < deadline )); do
  state="$(docker inspect --format '{{.State.Health.Status}}' jarvis-postgres 2>/dev/null || echo starting)"
  [[ "$state" == "healthy" ]] && break
  sleep 2
done

if [[ "$state" != "healthy" ]]; then
  warn "PostgreSQL did not become healthy in time. Check: docker compose logs postgres"
  exit 1
fi
printf '    postgres: healthy\n'

step "Running the environment healthcheck"
exec python "$REPO_ROOT/scripts/healthcheck.py"
