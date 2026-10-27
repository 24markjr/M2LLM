# JARVIS - API guide

Everything the console does goes through this API, so everything it does can be scripted. The
complete contract is `docs/openapi.json` (OpenAPI 3.1, regenerated and checked in CI); `/docs` on a
running server shows it, after sign-in.

## Authentication

Sign in once; the server sets an HttpOnly session cookie (`jarvis_session`, 12 hours) that every
later request sends.

```bash
curl -c jar -H 'content-type: application/json' \
     -d '{"email":"analyst@acme.example","password":"…"}' https://<site>/api/v1/auth/login
curl -b jar https://<site>/api/v1/auth/me
```

Every route under `/api/v1` needs a session, except `POST /auth/login`. Unauthenticated: `401`.
A role that may not: `403`. Another organisation's resource: `404`. Errors are always
`{"error_code", "message", "run_id", "details"}`. Limits: 600 requests a minute per account (120
writes), `429` with `Retry-After` beyond.

## An investigation, end to end

```bash
# 1. Upload files (multipart). Each is evidence from now on; the answer says how it was read.
curl -b jar -F files=@ledger.pdf -F files=@contract.docx \
     "https://<site>/api/v1/documents?case=CASE-2026-00012"

# 2. Start an investigation (202: accepted, not finished). queue_position > 0 means it is waiting.
curl -b jar -H 'content-type: application/json' https://<site>/api/v1/missions -d '{
  "objective": "Did spend exceed the approved budget, and who approved it?",
  "documents": ["ledger.pdf", "contract.docx"],
  "case_id": "CASE-2026-00012"}'

# 3. Follow it: poll, or stream server-sent events.
curl -b jar https://<site>/api/v1/missions/run_0123456789ab
curl -b jar -N https://<site>/api/v1/missions/run_0123456789ab/stream

# 4. Findings, each with its citations and verification.
curl -b jar https://<site>/api/v1/missions/run_0123456789ab/findings

# 5. The report: html (opens in a browser), pdf, docx, md or json. Each export is a signed version.
curl -b jar -o report.pdf \
     https://<site>/api/v1/missions/run_0123456789ab/investigation-report/export/pdf
```

`documents` are file names - of uploads, in your organisation - never paths.

## The conversation

```bash
# Ask; the answer is a thread with every claim's verdict and citations.
curl -b jar -H 'content-type: application/json' \
     https://<site>/api/v1/cases/CASE-2026-00012/conversation -d '{"text":"Who approved PO-77?"}'

# Streamed: activity, words, verdict events, then done with the thread.
curl -b jar -N -H 'content-type: application/json' \
     https://<site>/api/v1/cases/CASE-2026-00012/conversation/stream -d '{"text":"recheck F-002"}'
```

## Route groups

| Group | Prefix | For |
|---|---|---|
| Accounts | `/auth` | sign-in, people, organisations |
| Investigations | `/missions` | start, follow, findings, report, challenge, re-run, history |
| Files | `/documents` | upload, list |
| Evidence | `/evidence` | the locker, custody, integrity |
| Cases | `/cases` | cases, conversation, comparison, sources |
| Knowledge | `/missions/{id}/knowledge` | entities, claims, conflicts, timeline, graph |
| Memory | `/memory` | what past investigations established |
| Operations | `/ops`, `/governance` | metrics, cost, retention, data-subject requests, audit export (admins) |
