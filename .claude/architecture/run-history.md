# Run history: archives, records, deletion (Phase U1)

Code: `backend/app/api/archive.py`, `app/api/registry.py` (`from_archive`, `_restore`, `forget`).

## Investigations survive a restart (U1a)

The registry was memory alone. Runs were written to Postgres (`persistence.py`, Phase 3), but nothing
read them back, so after a restart the Missions list was empty while a case still listed its
investigations.

**The archive** is one JSON file per finished run, `.agent/runs/<run_id>.json` (gitignored): the
`MissionResult`, the events, the evidence ids it read and the text it read them as, page starts,
authority, its case, its knowledge graph and timeline, and its challenges. It is written when a run
ends (after the recording), again once the case has been told its outcome, and again whenever a
finding is challenged, so it always holds the run as the API last served it.

**Restoring** happens once per process, on the registry's first use (`get`, `records`, `create`):
every readable archive becomes a finished `MissionRecord` via `MissionRecord.from_archive`. A run
already in memory wins over its archive; an unreadable file is logged and skipped. Lists sort by
creation time, then sequence, so a restored run keeps its place among new ones.

Why a file and not the Postgres rows: the rows hold the run, tasks and findings, but not the text a
challenge searches, the knowledge view or the challenges, and the console without a database keeps
its history too. Postgres stays the durable *queryable* record; the archive is what lets every route
answer for an old run exactly as for a new one.

Why the stored text rather than re-reading the documents: a file can be re-uploaded with different
bytes. A challenge must search what the run read.

## Tests never write into `.agent/` (BUG-040)

`tests/conftest.py` points recordings and archives at the test's temporary folder for every test.

## Recordings as records, and deleting them (U1b)

`list_recordings` now reads each recording's final snapshot for what the run found (`findings`,
`verified`) and its `case_id`, and marks a recording `hidden`, with the reason, when:

- the run failed or was cancelled and found nothing (`HIDDEN_EMPTY`), or
- another file holds the same run (`HIDDEN_DUPLICATE`; a committed copy is preferred, else the newest).

Hidden recordings are left out of `GET /recordings` unless `include_hidden=true`. They are never
deleted automatically: deleting is the person's decision.

`DELETE /recordings/{name}` removes one local recording (`*.local.json`). A committed recording (a
renamed demo file in the repository) is refused with `RECORDING_KEPT`: it is removed with git, not
from the console. `DELETE /recordings?scope=hidden|all&confirm=delete` removes many and reports
`deleted` and `kept`; without `confirm=delete` it is refused (`CONFIRMATION_REQUIRED`), so a stray
request cannot empty the history. Every deletion is in the audit log (`recording.deleted`,
`recordings.deleted` with counts), besides the middleware's entry for the request itself.

Deleting a recording leaves the investigation: the archive still restores it. Deleting an
investigation (U1c) removes both.

## Deleting investigations and cases (U1c)

Code: `backend/app/api/deletion.py`.

An investigation lives in several places, and `delete_investigation` removes it from each, listing
what it removed:

| Where | Removed by |
|---|---|
| The registry | `MissionRegistry.forget` |
| Its archive | `archive.delete_archive` |
| Its local recordings | `recording.delete_recording` (committed ones are kept) |
| The stored run, with its tasks, findings, events and episodic memory | `RunRepository.delete`; every child table cascades from `agent_runs` |
| Its support for facts in semantic memory | `api/v1/memory.forget_quietly` (the existing forget route; None when memory is off) |
| Its place in its case | `CaseStore.remove_investigation` |

**Kept, by design, and said so in every response (`kept`):** the evidence's chain of custody, review
decisions and the audit log. All three are append-only by database trigger; none references
`agent_runs`, so the cascade never touches them. The audit log gains `mission.deleted` with the
list of what went.

A running investigation is refused (`409 MISSION_RUNNING`): cancel it first. Deleting every
investigation (`DELETE /missions?confirm=delete`) skips running ones and names them.

**A case** (`DELETE /cases/{id}`) is deleted with every investigation in it, each as above, and its
links to evidence. The evidence items stay in the Evidence Locker: they can belong to other cases,
and an item's existence is part of its custody. If any of its investigations is running, nothing is
deleted.

Memory is still reached only through the API's memory routes: deletion calls `forget_quietly` in
`api/v1/memory.py`, so the boundary test (`test_memory_boundary.py`) is unchanged.

## Rename, pin and search cases (U1d)

- **Rename**: `PATCH /cases/{id}` with `title` (it always could; the new sidebar uses it).
- **Pin**: `PATCH /cases/{id}` with `pinned`. `Case.pinned`, column `cases.pinned` (migration
  `au1c0a5e0001`, default false). Pinned cases come first; within each group the order stays newest
  first.
- **Search**: `GET /cases?q=...` keeps a case when every word of `q` appears in its id, title or
  description, or in the question of one of its investigations - so "shipment 4821" finds the case
  in which that was asked. Words, not meaning: search by meaning over evidence is the workspace
  search (Phase 40), and the Ctrl+K search in U3 combines both.

## The audit page, and stores that fall back to memory (U1e)

**What was found.** The audit page showed 0 entries. The `audit_log` table existed and accepted
writes (checked inside a rolled-back transaction); it held nothing because nothing had been written
through the API since Phase 50 created it - command-line evaluations do not pass through the API.
But a second cause was possible and invisible: the case, evidence and review stores probed the
database once per process and remembered a failure for ever. An API started a moment before
Postgres kept everything in memory until restarted, and the page could not say so.

**What changed.**

- `database/session.recheck(available, checked_at)`: a failed check is retried after 30 seconds
  (`RETRY_UNAVAILABLE_S`); a success is kept. Used by `get_case_store`, `get_locker` and
  `get_review_store`. A value set without a check time (what the tests set) is never re-probed, so a
  unit test cannot reach the real database.
- `GET /api/v1/system/stores` names the store behind cases, evidence, the audit log and
  investigations, with a note when one is in memory.
- The Audit page shows that store, the in-memory warning when it applies, and, when the log is empty,
  what will appear there.
