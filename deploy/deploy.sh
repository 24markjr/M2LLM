#!/usr/bin/env bash
# Deploy JARVIS to the Tessera VM, or roll back (v4 Phase 1b). Run from the repository root:
#
#   deploy/deploy.sh            build both images at HEAD, push them, start them on the VM
#   deploy/deploy.sh rollback   start the previously deployed tag again (no build)
#
# Uses only the `tessera` gcloud profile (chackomartin123@gmail.com), never the machine default.
# Images are tagged by git commit, so what runs is always a commit you can check out.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=tessera

REGISTRY=asia-south1-docker.pkg.dev/tessera-jarvis/tessera
VM=(--zone=asia-south1-a --tunnel-through-iap --quiet)
remote() { gcloud compute ssh tessera-vm "${VM[@]}" --command="$1"; }

if [[ "${1:-}" == "rollback" ]]; then
  remote 'cd /opt/tessera && test -s TAG.previous && T=$(cat TAG.previous) && sudo ./vm-env.sh "$T" \
    && sudo docker compose -p tessera -f docker-compose.prod.yml --env-file .env pull -q \
    && sudo docker compose -p tessera -f docker-compose.prod.yml --env-file .env up -d \
    && sudo cp TAG TAG.rolledback && echo "$T" | sudo tee TAG >/dev/null && echo "rolled back to $T"'
  exit 0
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "commit first: a deployment is always a commit" >&2
  exit 1
fi
TAG="$(git rev-parse --short HEAD)"

# The release gate (v4 Phase 9): a red benchmark blocks the deploy before anything is built.
PYTHON="backend/.venv/Scripts/python"; [[ -x "$PYTHON" ]] || PYTHON="backend/.venv/bin/python"
"$PYTHON" backend/scripts/release_gate.py || { echo "release gate is red: not deploying" >&2; exit 1; }

for image in backend web; do
  docker build -q -f "deploy/Dockerfile.${image}" -t "${REGISTRY}/jarvis-${image}:${TAG}" .
  docker push -q "${REGISTRY}/jarvis-${image}:${TAG}"
done

gcloud compute scp "${VM[@]}" --recurse \
  deploy/docker-compose.prod.yml deploy/vm-env.sh deploy/backup.sh deploy/restore.sh deploy/sql-init \
  tessera-vm:/tmp/tessera-deploy/ 2>/dev/null || {
  remote 'mkdir -p /tmp/tessera-deploy'
  gcloud compute scp "${VM[@]}" --recurse \
    deploy/docker-compose.prod.yml deploy/vm-env.sh deploy/backup.sh deploy/restore.sh deploy/sql-init \
    tessera-vm:/tmp/tessera-deploy/
}

remote "set -e; sudo cp -r /tmp/tessera-deploy/* /opt/tessera/ && sudo chmod 700 /opt/tessera/*.sh \
  && cd /opt/tessera && (test -s TAG && sudo cp TAG TAG.previous || true) \
  && sudo ./vm-env.sh ${TAG} \
  && sudo docker compose -p tessera -f docker-compose.prod.yml --env-file .env pull -q \
  && sudo docker compose -p tessera -f docker-compose.prod.yml --env-file .env up -d \
  && echo ${TAG} | sudo tee TAG >/dev/null && echo deployed ${TAG}"

# After the deploy, the outside view (v4 Phase 8): headers, every route refusing anonymous, ports.
"$PYTHON" backend/scripts/security_check.py "https://${SITE:-8.231.91.94.sslip.io}"   || echo "WARNING: the security check found problems - see above" >&2
