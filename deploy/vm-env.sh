#!/usr/bin/env bash
# On the VM (v4 Phase 1b): write /opt/tessera/.env from Secret Manager, readable by root only.
# Passwords never sit in the repository or on a laptop; rotating one is a new secret version and a
# re-run of this script.   sudo /opt/tessera/vm-env.sh <image tag>
set -euo pipefail

TAG="${1:?usage: vm-env.sh <image tag>}"
secret() { gcloud secrets versions access latest --secret="$1" --project=tessera-jarvis; }

umask 077
cat > /opt/tessera/.env <<ENV
REGISTRY=asia-south1-docker.pkg.dev/tessera-jarvis/tessera
TAG=${TAG}
SITE_ADDRESS=${SITE_ADDRESS:-8.231.91.94.sslip.io}
POSTGRES_PASSWORD=$(secret tessera-postgres-password)
NEO4J_PASSWORD=$(secret tessera-neo4j-password)
ADMIN_EMAIL=${ADMIN_EMAIL:-chackomartin123@gmail.com}
ADMIN_PASSWORD=$(secret tessera-admin-password)
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://100.104.34.93:11434}
COOKIE_SECURE=true
BACKUP_BUCKET=gs://tessera-jarvis-backups
ENV
echo "wrote /opt/tessera/.env for ${TAG}"
