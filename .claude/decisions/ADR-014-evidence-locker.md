# ADR-014 — Evidence is content-addressed, and its custody is append-only in the database

## Status

Accepted — 2026-10-07 (Phase 43)

## Context

Until Phase 43 a document was a file in a folder, known by its name. An investigation someone will
rely on has to answer: which exact bytes were examined, where did they come from, who brought them
in, and what happened to them between arrival and the finding that cites them? A name answers none
of that - the same name can hold different bytes tomorrow. The v2 review called this the gap
between a document analyser and an investigation platform.

## Decision

1. **Identity is the SHA-256 of the bytes.** An evidence item is numbered (`EV-000001`) but
   identified by its hash; the same bytes are one item however often they arrive, and changed bytes
   under the same name are a new item.
2. **The original is stored content-addressed and write-once** (`.agent/evidence/<2 hex>/<sha256>`),
   separate from the working copy the parsers read. Only `app/evidence/store.py` writes there.
3. **Custody is an append-only log, enforced by Postgres**, not by convention: a trigger rejects
   UPDATE, DELETE and TRUNCATE on `custody_events`, and the foreign key forbids deleting an item with
   a history. The application can add to the chain and never alter it.
4. **Integrity is checked before a mission reads evidence.** A mismatch excludes the file and is
   recorded; the mission says what it left out and why.
5. **Postgres when available, memory otherwise - and named.** Consistent with retrieval (ADR-013): the
   locker never fails a run (invariant 10), and when it is the memory locker, the API and page say
   custody is not durable.

## Alternatives considered

- **A JSONL custody file** (Member 2's provenance tracker wrote one). Simple, but anyone with the file
  can edit or truncate it, and nothing would notice. A database trigger makes rewriting history an
  error, not a choice.
- **A hash chain** (each event hashing the previous). Detects tampering after the fact rather than
  preventing it; worth adding when custody must be verified outside this database (export, Phase 51).
- **Keying items by name.** What existed; it is exactly what cannot prove which bytes were read.

## Consequences

- Tests cannot clean up custody, so none may write it to a real database except inside a rolled-back
  transaction; `tests/conftest.py` gives every test a memory locker and a temporary store.
- Editing an uploaded file on disk is now an integrity failure, by design. Editing a repository
  fixture is a new version (fixtures change through version control).
- Disk use grows with every distinct file version; nothing is garbage-collected, also by design.
