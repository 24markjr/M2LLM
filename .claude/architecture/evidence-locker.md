# The Evidence Locker (Phase 43)

Every input becomes an evidence item with a provable history. Code: `app/schemas/evidence_locker.py`,
`app/evidence/` (`store.py`, `locker.py`, `service.py`), `app/database/evidence_locker.py`,
`app/api/v1/evidence.py`; migration `a43e0c1d0001`. UI: `#/evidence` and `#/evidence/EV-000001`
(`frontend/src/pages/EvidencePage.tsx`). Decision: [ADR-014](../decisions/ADR-014-evidence-locker.md).

## The model

| | |
|---|---|
| **Evidence item** | `EV-000001`; identified by the **SHA-256 of its bytes** (the same bytes are one item, however often they arrive); name, kind, parser, size, collected at/by, source, classification, integrity |
| **Custody event** | One link in the chain: ACQUIRED, HASHED, STORED, IMPORTED, PARSED, PARSE_FAILED, UNDERSTOOD, INDEXED, ANALYSED, CITED, REPORTED, VERIFIED, INTEGRITY_FAILED, METADATA_CHANGED; actor, time, details |
| **Stored original** | `.agent/evidence/<2 hex>/<sha256>`, write-once, read-only, gitignored |
| **Working copy** | `.agent/uploads/<name>` (or the fixture file): what the parsers read |

## The chain, end to end

```
upload ──> ACQUIRED ─> HASHED ─> STORED ─> PARSED (or PARSE_FAILED) ─> UNDERSTOOD (media) ─> INDEXED (background)
fixture or earlier upload, first used ──> IMPORTED ("earlier history unknown")
mission ──> integrity check ─> ANALYSED (run id)            ... run ... ─> CITED (finding, locator, claim)
person ──> VERIFIED / INTEGRITY_FAILED (re-verify) · METADATA_CHANGED (from -> to)
```

## Rules

1. **Append-only, enforced by the database.** A trigger on `custody_events` raises on UPDATE, DELETE
   and TRUNCATE; the foreign key has no cascade, so an item with a history cannot be deleted either.
   Tests in `tests/integration/test_evidence_locker.py` try all four.
2. **Integrity before every mission.** The stored original and the working copy must both hash to the
   recorded SHA-256. A mismatch marks the item FAILED, records INTEGRITY_FAILED, and the mission
   leaves the file out and says why (`excluded_documents`); if nothing is left, it is refused
   (`NO_READABLE_DOCUMENTS`, naming the integrity failure). Findings that cited the item are listed on
   its page as resting on failed evidence.
3. **A changed upload is tampering; a changed fixture is a new version.** Only intake writes the
   uploads folder, so a working copy that no longer matches the item last acquired under its name was
   changed behind custody's back. Fixtures change through version control, so changed fixture bytes
   are registered as a new, IMPORTED version. (Phase 43's own test found that the first version
   registered tampered uploads as fresh items.)
4. **A mission links to the exact version it read.** `MissionDetail.evidence` maps each document name
   to the evidence id admitted, so a citation opens that item, not whatever is newest under the name.
5. **Only the store writes the evidence folder** (an invariant test parses the source).
6. **Never failing an upload or a run** (invariant 10). The locker is Postgres when the database
   answers and memory otherwise; memory is named (`locker: memory`) and the page warns that custody
   recorded then is not durable. Any locker error is logged and the work proceeds without custody.
7. **Tests never write custody to a developer's database.** Every test gets a fresh memory locker and
   a temporary evidence folder; the Postgres tests run inside a transaction they roll back - an
   append-only table cannot be cleaned up afterwards.
8. **File work off the event loop.** Hashing and copying (a video can be 500 MB) run on a worker
   thread.

## Who records what

| Event | Recorded by |
|---|---|
| ACQUIRED, HASHED, STORED | `service.intake`, from the upload endpoint |
| PARSED / PARSE_FAILED, UNDERSTOOD | the upload endpoint, after parsing |
| INDEXED | the background indexing task |
| IMPORTED | `service.register`, the first time a mission (or the locker list) meets a file |
| INTEGRITY_FAILED | `service.verify`, before a mission or on demand |
| ANALYSED | the missions endpoint, once the run exists |
| CITED | the registry, when the run ends, per finding and locator |
| VERIFIED, METADATA_CHANGED | the evidence API, with the `X-Jarvis-User` actor |
| REPORTED | reserved for Phase 51 (report export) |

Evaluation runs and the CLI record no custody, as they store no runs.

## What it does not do yet

Cases (Phase 44) will own evidence (`case_id` is present, unused); people are named by a header
until accounts exist (Phase 55); evidence is not encrypted at rest (Phase 55); a report is not yet a
custody event (Phase 51).
