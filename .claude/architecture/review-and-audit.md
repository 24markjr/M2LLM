# Human review and the audit log (Phase 50)

Decision record: ADR-016.

## Which findings need a person (`.agent/config/review.yaml`, `review/service.py` `requirements`)

| Rule | Reason shown |
|---|---|
| statement type CONTRADICTION | it reports a contradiction |
| a DESCRIBED_ONLY verification issue | the verifier found it only described, not established |
| a challenge CONTESTED or OVERTURNED it (Phase 48) | a challenge contested it |
| statement type RISK or RECOMMENDATION | it is a risk: a judgement |
| its case is HIGH or CRITICAL | its case is HIGH |
| it maps to an ATT&CK technique (Phase 53) | it maps to a MITRE ATT&CK technique |

A finding no rule names needs no review: verified, it counts as before.

## Decisions

`PENDING` -> `APPROVED` / `REJECTED` / `MODIFIED`, each a new `ReviewDecision` (reviewer from
`X-Jarvis-User`, time, reason; REJECTED and MODIFIED must give a reason, MODIFIED the reworded claim).
The latest decision is the state; the history stays. `POST .../findings/{id}/review`,
`GET .../reviews`.

- **Approval** (or modification) of a verified finding releases the facts it cites into semantic
  memory (`memory.service.remember_approved`), audited as `memory.facts_released`.
- **Rejection** with `replan: true` starts a follow-up investigation: the same question over the same
  documents in the same case, told which finding was rejected and why (`mission.follow_up`).
- **Memory at the end of a run** records every finding as an episode but no fact from a finding still
  awaiting review (`record_run(held=...)`); when the rules cannot be evaluated, everything is held.
- `counts_as_established(finding, review)`: verified, and needing no review or approved - what the
  report (Phase 51) will use.

## The audit log

- **Every write**: an HTTP middleware (`app/api/app.py` `audit_writes`) records each POST, PUT,
  PATCH and DELETE under `/api/` - actor, method and path, target, status code - refused writes
  included. A test enumerates every write route in the OpenAPI schema, calls it, and checks each left
  an entry.
- **The system's own actions**: `mission.finished`, `review.approved|rejected|modified`,
  `memory.facts_released`, `mission.follow_up`.
- `GET /api/v1/audit?target=&limit=`; the console's Audit page.

## Storage

`review_decisions` and `audit_log` (migration `a50a0d17e001`), both append-only by trigger like
custody (an UPDATE, DELETE or TRUNCATE raises). Postgres when available, memory otherwise, named in
the response (`store`). Tests use a memory store; the Postgres tests run in a rolled-back
transaction.
