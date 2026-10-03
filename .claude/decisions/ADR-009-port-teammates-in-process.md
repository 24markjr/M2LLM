# ADR-009 — Port Members 3 and 4 into the backend, not call them as services

## Status

Accepted — 2026-10-03

## Context

Member 3 (knowledge graph) and Member 4 (memory, trust, security, evaluation) delivered working
standalone Python projects. Member 1's architecture already had seams for both:
`VerificationProvider` with a `RemoteVerifier` adapter, and a `KNOWLEDGE_PROVIDER` setting with no
adapter behind it yet. The original plan
([member-1-scope.md](../context/member-1-scope.md)) was for each member to run a service that
Member 1 calls through a protocol, and **never import another member's implementation directly**.

What actually arrived does not fit that plan:

- Member 4 has **no HTTP service**. It is a library: `verify_claim(claim, evidence_pool)`.
  `RemoteVerifier` posts to a `/verify` endpoint that does not exist, and its result type differs
  from JARVIS's.
- Member 3 has a FastAPI service, but it calls the model with `requests` and a hard-coded model
  name, and keeps every ingest in **one global SQLite file**. Called as a service, claims from
  one mission show up in the next mission's contradictions. The evaluation suite runs eight
  missions back to back, so a negative scenario would inherit contradictions planted in a
  positive one.
- Neither runs under `mypy --strict`, and both print instead of logging.

Two options were considered.

## Decision

**Re-implement both teammates' features inside `backend/app/`, preserving their logic, and
then remove the extracted folders.** Their original source is archived verbatim in
[`.claude/integrations/originals/`](../integrations/originals/). Every feature, its original
behaviour, and every deliberate deviation is recorded in
[`teammate-port.md`](../integrations/teammate-port.md).

The user made this decision on 2026-10-03: "retrieve all the features built by them and we'll
make it with the same logic they built it, but in our way and more practical."

## Why not run them as services

**(b) Keep their FastAPI apps and call them over HTTP** was the alternative. It keeps their code
untouched and honours the original boundary rule. It was rejected because:

1. **It does not fix what is wrong.** The global SQLite file and the direct model call are inside
   their code. An HTTP adapter in front of them does not scope a database to a run.
2. **Member 4 would need a service written for it anyway**, which is a port by another name.
3. **Three processes for a demo.** The demo currently needs Ollama and one Python process.
   Adding two more services that must be running, on the right ports, before a mission works is
   a real cost for no capability gained.
4. **The invariants are tested, not hoped for.** In-process code is checked by
   `test_llm_isolation.py`, `test_invariants.py` and `mypy --strict`. A service on another port
   is checked by nothing in this repository.

## What "the same logic, our way" means

Kept exactly: the algorithms, thresholds and status vocabularies. Examples are TF-IDF with
relevance 0.2, support 0.4 and conflict 0.5; the shared-ID-and-disjoint-times conflict rule;
grouping by (entity, attribute); the +3/+1/+n/+1 search score; the five injection categories and
their severity rule.

Changed, always with a measured reason recorded in `teammate-port.md`:

- **Where it runs.** The model is reached through `LLMProvider` and a versioned prompt. State is
  per run. Persistence goes to PostgreSQL through the existing optional-persistence path.
- **Types.** Pydantic models with `extra="forbid"`, as everywhere else.
- **Defects the port exposed.** Each is fixed and logged in the bug log: dates forced to 2026,
  claims stored under raw names, search returning every claim, the verifier missing date
  conflicts, and the overlap fallback passing wrong dates.

## Consequences

- The `RemoteVerifier` and remote knowledge adapters remain. If either teammate later deploys a
  real service, it can still swap in at the same seam.
- **Teammates' later changes do not flow in automatically.** A change Member 3 or 4 makes to
  their own repository after 2026-10-03 must be ported by hand. `teammate-port.md` is the place
  to record what was ported and when.
- Credit stays with them. The docstring of every ported module names the original file it came
  from.
