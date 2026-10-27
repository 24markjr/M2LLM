#!/usr/bin/env bash
# Restore a backup made by backup.sh (v4 Phase 1b). Stops the backend, replaces the database and the
# evidence, runs/traces volumes with the backup's, checks the SHA-256 of every file first, and starts
# the stack again. Destructive by design: it asks before it replaces anything.
#   ./restore.sh gs://tessera-jarvis-backups/20261027T021500Z
set -euo pipefail

SOURCE="${1:?usage: restore.sh <backup folder, gs://... or a local path>}"
PROJECT="${COMPOSE_PROJECT:-tessera}"
# On-premise (v4 Phase 10): COMPOSE_PROJECT=jarvis COMPOSE_FILE=./docker-compose.onprem.yml ENV_FILE=./.env
COMPOSE=(docker compose -p "$PROJECT" -f "${COMPOSE_FILE:-/opt/tessera/docker-compose.prod.yml}"
         --env-file "${ENV_FILE:-/opt/tessera/.env}")
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ "$SOURCE" == gs://* ]]; then
  gcloud storage cp "${SOURCE}/*" "$WORK/"
else
  cp "$SOURCE"/* "$WORK/"
fi
# Backups before v4 Phase 10 named their files by absolute temporary paths: check them by name.
sed -i -E 's#  /[^ ]*/([^/]+)$#  \1#' "$WORK/SHA256SUMS"
(cd "$WORK" && sha256sum -c SHA256SUMS)

read -r -p "Replace the live database and evidence with ${SOURCE}? Type 'restore': " answer
[[ "$answer" == "restore" ]] || { echo "nothing changed"; exit 1; }

"${COMPOSE[@]}" stop web backend
docker exec -i "${PROJECT}-postgres-1" pg_restore -U jarvis -d jarvis --clean --if-exists < "$WORK/jarvis.dump"
for volume in agent-evidence agent-runs agent-traces; do
  docker run --rm -v "${PROJECT}_${volume}:/data" -v "$WORK:/in:ro" alpine \
    sh -c "rm -rf /data/* && tar -xzf /in/${volume}.tar.gz -C /data"
done
"${COMPOSE[@]}" up -d
echo "restored ${SOURCE}"
