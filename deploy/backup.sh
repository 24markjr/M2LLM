#!/usr/bin/env bash
# Nightly backup (v4 Phase 1b): Postgres (custom-format dump) and the evidence volume, to a Cloud
# Storage bucket with versioning and a 30-day lifecycle - or, on-premise (Phase 10), to a local
# folder (BACKUP_BUCKET=/srv/backups). Run by cron as root:
#   15 2 * * * /opt/tessera/backup.sh >> /var/log/tessera-backup.log 2>&1
#
# Neo4j is not dumped: its knowledge graph is rebuilt from each archived run (.agent/runs), and the
# runs volume is backed up below. Restore: deploy/restore.sh.
set -euo pipefail

BUCKET="${BACKUP_BUCKET:?set BACKUP_BUCKET: gs://tessera-jarvis-backups, or a local folder}"
PROJECT="${COMPOSE_PROJECT:-tessera}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

docker exec "${PROJECT}-postgres-1" pg_dump -U jarvis -d jarvis -Fc > "$WORK/jarvis.dump"
for volume in agent-evidence agent-runs agent-traces; do
  docker run --rm -v "${PROJECT}_${volume}:/data:ro" -v "$WORK:/out" alpine \
    tar -czf "/out/${volume}.tar.gz" -C /data .
done
# Names relative to the backup, so restore.sh can check them wherever it unpacks them. (Absolute
# temporary paths were written here until v4 Phase 10, and no restore could pass its check.)
(cd "$WORK" && sha256sum -- * > SHA256SUMS)

if [[ "$BUCKET" == gs://* ]]; then
  gcloud storage cp "$WORK"/* "${BUCKET}/${STAMP}/"
else
  mkdir -p "${BUCKET}/${STAMP}" && cp "$WORK"/* "${BUCKET}/${STAMP}/"
fi
echo "backup ${STAMP}: $(du -sh "$WORK" | cut -f1) -> ${BUCKET}/${STAMP}/"
