# JARVIS - On-premise and air-gapped installation

For a customer whose documents may not leave their network. The same product as the cloud, with the
model running on the customer's own server and nothing fetched from the internet.

## What is in a bundle

`jarvis-onprem-<version>.tar.gz`, built by `deploy/onprem/make-bundle.sh` on a machine with
internet:

- the JARVIS images (backend, web) at one commit, and the Postgres, Neo4j and Ollama images;
- the pinned models: the language model and the embedding model (Ollama's manifests and blobs), and
  the entailment model used in verification;
- `docker-compose.onprem.yml`, `docker-compose.gpu.yml`, `install.sh`, the backup and restore
  scripts, and `SHA256SUMS` over every file.

## The server

- Linux, 64-bit, Docker Engine with the compose plugin.
- 8 CPU cores, 32 GB RAM, 200 GB disk for a small team; more disk for more evidence.
- An NVIDIA GPU with 8 GB or more, and the NVIDIA container toolkit, for usable speed. Without one the
  model runs on the CPU: investigations work, several times slower.
- A hostname for the server inside the network (e.g. `jarvis.corp.example`).

## Installing

```bash
tar -xzf jarvis-onprem-<version>.tar.gz && cd jarvis-onprem-<version>
sudo ./install.sh jarvis.corp.example admin@corp.example
```

The installer checks every file against `SHA256SUMS`, loads the images, puts the models in place,
writes `.env` with fresh random passwords (readable by root only), starts the stack and prints the
first administrator's password once. Sign in at `https://jarvis.corp.example` and change it.

HTTPS uses a certificate from the server's own local authority (there is no Let's Encrypt inside a
closed network). Install its root certificate on the client machines, or put the server behind the
customer's own TLS proxy:

```bash
docker compose -p jarvis exec web cat /data/caddy/pki/authorities/local/root.crt
```

## Upgrading

Unpack the newer bundle beside the old one, copy the old `.env` into it, and run `install.sh` again
with the same arguments. Data volumes are kept; database migrations run before the backend starts.

## Running it

- **Backups**: `COMPOSE_PROJECT=jarvis BACKUP_BUCKET=/srv/backups ./backup.sh` writes to a local
  folder; schedule it nightly and copy the folder off the server. To restore:
  `COMPOSE_PROJECT=jarvis COMPOSE_FILE=./docker-compose.onprem.yml ENV_FILE=./.env ./restore.sh
  /srv/backups/<stamp>` - it checks every sum and asks before replacing anything.
- **Watch folders**: a case can watch a folder on the server (Case > Watch folder). Point a network
  share or a scanner at it; files dropped there become evidence within five minutes.
- Everything else - organisations, people, retention, data-subject requests, the audit log - is the
  same as the cloud: see the [admin guide](admin-guide.md).

## What is not included

- Indian-language processing through Bhashini needs the internet and is not part of an air-gapped
  installation; the open-source language models (when added) are.
- The release gate runs where the bundle is built, not on the customer's server.
