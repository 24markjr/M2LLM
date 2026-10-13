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
