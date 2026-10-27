#!/usr/bin/env bash
# Install JARVIS from an on-premise bundle (v4 Phase 10). No internet needed. Run as root (or a
# member of the docker group) on a Linux server with Docker and the compose plugin, from inside the
# unpacked bundle:
#
#   sudo ./install.sh jarvis.corp.example admin@corp.example
#
# Checks every file against SHA256SUMS, loads the images, puts the models in place, writes .env with
# fresh random secrets (readable by root only), starts the stack, and prints the first admin's
# password once. Re-running it upgrades: the data volumes and .env are kept.
set -euo pipefail

SITE="${1:?usage: install.sh <hostname> <admin email>}"
ADMIN="${2:?usage: install.sh <hostname> <admin email>}"
cd "$(dirname "$0")"
source VERSION

echo "==> checking the bundle"
sha256sum --quiet -c SHA256SUMS

echo "==> loading images"
gunzip -c images/jarvis-images.tar.gz | docker load -q

COMPOSE=(docker compose -p jarvis -f docker-compose.onprem.yml --env-file .env)
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  COMPOSE+=(-f docker-compose.gpu.yml)
  echo "==> NVIDIA GPU found: the model runs on it"
else
  echo "==> no GPU found: the model runs on the CPU (slow; see docs/guides/on-premise.md)"
fi

new_install=0
if [[ ! -f .env ]]; then
  new_install=1
  secret() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 28; }
  admin_password="Jv-$(secret)9a"
  umask 077
  cat > .env <<ENV
TAG=${TAG}
OLLAMA_TAG=${OLLAMA_TAG}
SITE_ADDRESS=${SITE}
POSTGRES_PASSWORD=$(secret)
NEO4J_PASSWORD=$(secret)
ADMIN_EMAIL=${ADMIN}
ADMIN_PASSWORD=${admin_password}
ENV
else
  sed -i "s/^TAG=.*/TAG=${TAG}/; s/^OLLAMA_TAG=.*/OLLAMA_TAG=${OLLAMA_TAG}/" .env
fi

echo "==> models"
"${COMPOSE[@]}" create ollama backend >/dev/null
docker run --rm -v jarvis_ollama-models:/root/.ollama -v "$PWD/models/ollama:/in:ro" alpine \
  sh -c "mkdir -p /root/.ollama/models && cp -r /in/. /root/.ollama/models/"
if [[ -d models/media-cache/models ]]; then
  docker run --rm -v jarvis_agent-media-cache:/cache -v "$PWD/models/media-cache:/in:ro" alpine \
    sh -c "cp -r /in/models /cache/ && chown -R 10001:10001 /cache"
fi

echo "==> starting"
"${COMPOSE[@]}" up -d
for _ in $(seq 1 60); do
  if docker inspect -f '{{.State.Health.Status}}' jarvis-backend-1 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 5
done
"${COMPOSE[@]}" ps

echo
echo "JARVIS ${TAG} is at https://${SITE}"
if [[ $new_install == 1 ]]; then
  echo "First admin: ${ADMIN}  password: ${admin_password}"
  echo "Sign in and change it now (Settings > Your account). It is also in .env, readable by root."
fi
echo "The certificate is from Caddy's local authority: install its root on client machines"
echo "  docker compose -p jarvis exec web cat /data/caddy/pki/authorities/local/root.crt"
