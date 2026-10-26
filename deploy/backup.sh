#!/usr/bin/env bash
# Nightly backup on the VM (v4 Phase 1b): Postgres (custom-format dump) and the evidence volume, to
# a Cloud Storage bucket with versioning and a 30-day lifecycle. Run by cron as root:
#   15 2 * * * /opt/tessera/backup.sh >> /var/log/tessera-backup.log 2>&1
#
# Neo4j is not dumped: its knowledge graph is rebuilt from each archived run (.agent/runs), and the
# runs volume is backed up below. Restore: deploy/restore.sh.
set -euo pipefail

BUCKET="${BACKUP_BUCKET:?set BACKUP_BUCKET, e.g. gs://tessera-jarvis-backups}"
PROJECT="${COMPOSE_PROJECT:-tessera}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

docker exec "${PROJECT}-postgres-1" pg_dump -U jarvis -d jarvis -Fc > "$WORK/jarvis.dump"
for volume in agent-evidence agent-runs agent-traces; do
  docker run --rm -v "${PROJECT}_${volume}:/data:ro" -v "$WORK:/out" alpine \
    tar -czf "/out/${volume}.tar.gz" -C /data .
done
sha256sum "$WORK"/* > "$WORK/SHA256SUMS"

gcloud storage cp "$WORK"/* "${BUCKET}/${STAMP}/"
echo "backup ${STAMP}: $(du -sh "$WORK" | cut -f1) -> ${BUCKET}/${STAMP}/"
