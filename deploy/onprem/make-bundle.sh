#!/usr/bin/env bash
# Build an on-premise bundle of JARVIS (v4 Phase 10), on a machine with internet, for a machine
# without. Run from the repository root:
#
#   deploy/onprem/make-bundle.sh                 # images, models and installer in dist/
#   OLLAMA_MODELS_DIR=~/.ollama/models deploy/onprem/make-bundle.sh
#
# The bundle holds: the JARVIS images built at HEAD, the database and model-server images, the
# pinned models (Ollama's manifests and blobs; the entailment model's cache), the compose files and
# the installer. Nothing in it is fetched again at install time.
set -euo pipefail

TAG="$(git rev-parse --short HEAD)"
OUT="dist/jarvis-onprem-${TAG}"
MODELS=(${JARVIS_MODELS:-qwen3:4b nomic-embed-text})
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"
OLLAMA_TAG="${OLLAMA_TAG:-0.12.6}"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "commit first: a bundle is always a commit" >&2
  exit 1
fi
rm -rf "$OUT" && mkdir -p "$OUT/images" "$OUT/models/ollama" "$OUT/models/media-cache"

echo "==> images (${TAG})"
docker build -q -f deploy/Dockerfile.backend -t "jarvis-backend:${TAG}" .
docker build -q -f deploy/Dockerfile.web -t "jarvis-web:${TAG}" .
for image in pgvector/pgvector:pg16 neo4j:5-community "ollama/ollama:${OLLAMA_TAG}"; do docker pull -q "$image"; done
docker save "jarvis-backend:${TAG}" "jarvis-web:${TAG}" pgvector/pgvector:pg16 neo4j:5-community \
  "ollama/ollama:${OLLAMA_TAG}" | gzip -1 > "$OUT/images/jarvis-images.tar.gz"

echo "==> models: ${MODELS[*]}"
for model in "${MODELS[@]}"; do
  name="${model%%:*}"; tag="${model#*:}"; [[ "$tag" == "$model" ]] && tag=latest
  manifest="$OLLAMA_MODELS_DIR/manifests/registry.ollama.ai/library/$name/$tag"
  [[ -f "$manifest" ]] || { echo "missing $model in $OLLAMA_MODELS_DIR (ollama pull $model)" >&2; exit 1; }
  mkdir -p "$OUT/models/ollama/manifests/registry.ollama.ai/library/$name" "$OUT/models/ollama/blobs"
  cp "$manifest" "$OUT/models/ollama/manifests/registry.ollama.ai/library/$name/$tag"
  # Every layer the manifest names, by digest.
  for digest in $(grep -o 'sha256:[0-9a-f]\{64\}' "$manifest" | sort -u); do
    cp "$OLLAMA_MODELS_DIR/blobs/${digest/:/-}" "$OUT/models/ollama/blobs/"
  done
done
if [[ -d .agent/media-cache/models ]]; then
  cp -r .agent/media-cache/models "$OUT/models/media-cache/"   # the entailment model (Phase 2)
fi

echo "==> installer"
cp deploy/onprem/docker-compose.onprem.yml deploy/onprem/docker-compose.gpu.yml \
   deploy/onprem/install.sh deploy/backup.sh deploy/restore.sh "$OUT/"
cp -r deploy/sql-init "$OUT/"
echo "TAG=${TAG}" > "$OUT/VERSION"
echo "OLLAMA_TAG=${OLLAMA_TAG}" >> "$OUT/VERSION"
(cd "$OUT" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)
tar -C dist -czf "dist/jarvis-onprem-${TAG}.tar.gz" "jarvis-onprem-${TAG}"
echo "bundle: dist/jarvis-onprem-${TAG}.tar.gz ($(du -h "dist/jarvis-onprem-${TAG}.tar.gz" | cut -f1))"
