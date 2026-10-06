# Cases and the professional hierarchy (Phase 44)

Case → Investigations → Findings → Evidence → Reasoning, with the technical trace one level down.
Code: `app/schemas/case.py`, `app/cases/` (`store.py`, `service.py`), `app/database/case_store.py`,
`app/api/v1/cases.py`, `app/orchestration/labels.py`; migration `a44c0de50001`. UI: `#/` (cases),
`#/case/CASE-2026-00001`, `#/missions` (every investigation), the mission page's Professional view.

## The model

| | |
|---|---|
| **Case** | `CASE-<year>-<n>` from a sequence; title, description, severity (LOW-CRITICAL), status (OPEN, INVESTIGATING, REVIEW, CLOSED), owner, mode (GENERAL; CYBER from Phase 52), opened/closed |
| **Investigation in a case** | A mission's run id with the outcome it reached (status, findings, verified, contradictions, open gaps), written when it starts and again when it ends |
| **Evidence in a case** | A link to an Evidence Locker item; the same item can be in several cases |
| **Counters** | Computed on every read from the above (and the items' integrity), never stored |

## Rules

1. **A case survives a restart.** Missions live in the engine's memory; a case keeps its own record of
   each investigation and its outcome, so its page still lists them after a restart (links open the
   mission while the engine holds it, or its recording). Not a foreign key to `agent_runs`: a run is
   stored only when the database was up while it ran.
2. **Filing follows the work.** A mission started in a case files itself and the evidence it read; an
   upload with `?case=` files its item; existing items can be filed (`POST /cases/{id}/evidence`). An
   OPEN case becomes INVESTIGATING when its first investigation starts. A CLOSED case accepts no new
   investigation (409 `CASE_CLOSED`) until it is reopened.
3. **Never failing the work it files** (invariant 10). Postgres when available, memory otherwise -
   named on every response and on the pages.
4. **Tests never write cases to a real database**: a memory store per test; the Postgres store is
   tested inside a rolled-back transaction.

## The Professional view

The mission page opens in the **Professional view**: the phase tracker, the investigation as plain
steps with marks (✓ done, ↻ doing, ✗ failed, "added while investigating" for tasks the replanning loop
inserted), the **current conclusion** - only findings that passed independent verification, or a plain
statement that nothing did - then the findings with their evidence and the report. The **Technical
trace** (task graph, gaps, execution statistics, event timeline) is one click away and remembered per
browser.

Step labels come from the engine (`TaskNode.label`), one phrasing per task type in three tenses, chosen
by status. They describe what the task type does, never what a model said it did; a test fails if a
task type has no label.

## Not yet

Review states and the audit trail on a case (Phase 50); reports per case (Phase 51); cyber mode
(Phase 52); owners as real accounts (Phase 55).
