# JARVIS - Administrator guide

For the administrators of an organisation, and for the operator running a JARVIS installation.

## 1. Organisations and people

Each customer is an **organisation**. Its people, cases, files, investigations, memory and audit
log are its own: nothing of one organisation is visible to another, and a request for another's
run, case or file answers "not found".

- **The operator** - the administrators of the `default` organisation - creates organisations:
  **Settings > Organisations**, an id (`acme-bank`), and the organisation's first administrator.
- **An organisation's admin** adds its people: **Settings > People** - e-mail, name, role
  (viewer, reviewer, analyst, admin) and a first password (12+ characters, mixed case, a digit).
  Changing a role, deactivating or resetting a password signs the person out everywhere. An admin
  cannot demote or deactivate themselves.

## 2. Operations

**Settings > Operations** (admins): investigations over a period - completed, failed, the error rate,
median and 95th-percentile time, time waiting in the queue, model calls and tokens - and **cost**,
per investigation and in all.

Cost is an estimate from time, at the rates in the server's settings (`GPU_COST_PER_HOUR_INR`,
`SERVER_COST_PER_HOUR_INR`): the model's working time at the GPU's hourly rate, plus the run's
time at a share of the server's. A self-hosted model is paid for by the hour, not the token.

Investigations queue for `MAX_CONCURRENT_RUNS` slots (default 2), first come first served; up to 50
may wait. Each account may make 600 requests a minute, 120 of them changes.

## 3. Data governance

**Settings > Data governance** (admins):

- **Retention** - keep investigations for N days (0 = until deleted). Applied daily; "What would
  retention delete?" shows the list first. Evidence files and their chain of custody are kept: custody
  is append-only, and deleting evidence is a legal decision, not a timer's.
- **Masking** - with it on, exported reports show e-mail addresses, Indian phone numbers, Aadhaar,
  PAN and card numbers as `[email]`, `[aadhaar]`... Stored evidence is never altered.
- **Data-subject requests (DPDP Act 2023)** - find a person's name, e-mail or ID across the
  organisation's investigations (their documents, questions and findings) and case conversations;
  then erase: the investigations holding it are deleted and the messages mentioning it blanked.
  Evidence files holding it are listed for your legal-hold decision, not deleted. Both steps are in
  the audit log.
- **Audit log** - every change anyone made, and every sign-in, as CSV.
- **Bhashini** - off by default. Set to *Unclassified* or *Unclassified and Internal* to let
  Bhashini (MeitY's language platform) translate, transcribe and read aloud material of those
  levels. Confidential and Restricted material, and anything whose level is unknown, always stays
  on the open-source engine in our cloud, whatever this says. Needs `BHASHINI_USER_ID` and
  `BHASHINI_API_KEY` in Secret Manager (from Bhashini onboarding); without them this setting has no
  effect. If Bhashini fails, the open-source engine answers, and Operations counts the fallback.

**Operations** also shows **language engines**: calls, characters, failures and fallbacks per
engine (IndicTrans2, Bhashini, the local model for Roman-script questions).

## 4. The installation (operator)

The cloud installation runs on Google Cloud (project `tessera-jarvis`, Mumbai): one VM with the web
edge (HTTPS), the backend, Postgres with pgvector and Neo4j in containers; secrets in Secret Manager;
SSH only through Identity-Aware Proxy; ports 80 and 443 only. The model runs on a GPU machine joined
over Tailscale.

| Task | How |
|---|---|
| Deploy the current commit | `deploy/deploy.sh` - refuses an uncommitted tree; runs the release gate first; checks the live site afterwards |
| Roll back | `deploy/deploy.sh rollback` - the previous image tag, no build |
| Backups | nightly at 02:15 UTC to a versioned bucket kept 30 days: the database, evidence, runs and recordings, with SHA-256 sums |
| Restore | `/opt/tessera/restore.sh gs://tessera-jarvis-backups/<stamp>` - checks every sum, asks before replacing |
| Rotate a secret | add a version in Secret Manager, then deploy (the VM's settings are rewritten) |
| Check the outside view | `python backend/scripts/security_check.py https://<site>` |

The model link: the GPU machine runs Ollama listening on all interfaces, with a firewall rule
admitting only Tailscale addresses (`scripts/expose-ollama-tailscale.ps1`). When it is off, the
console works and `/health` says `degraded`; investigations wait for the model.

For an installation inside a customer's own network, see [on-premise](on-premise.md).

## 5. Releases

A release ships only through `deploy/deploy.sh`, which first runs the **release gate**
(`backend/scripts/release_gate.py`): the latest benchmark report must clear the floors in
`.agent/config/release_gate.yaml` - correct facts, supported sentences, citation precision, no
invented values, no false alarms, no crashed scenario, mean time per investigation, the whole suite
(multimodal included), and a report no older than 45 days. CI runs the same gate on every push. Red
blocks the release. Re-run the benchmark (`python -m app.evaluation.benchmark`) after any change to
prompts, models or reasoning, and commit its report.
