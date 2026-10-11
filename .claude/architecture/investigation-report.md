# The investigation report (Phase 51)

One structured object (`schemas/investigation_report.py`), built from the run as it stands
(`reporting/builder.py`) and drawn by every exporter from the same `sections()`. Decision on the PDF
writer: ADR-017.

## What it holds

| Part | From |
|---|---|
| header | report id, run, case, objective, model, generated at, **content hash** (SHA-256 of the content, not the time) |
| risk | the highest severity among *established* findings, with the finding and rule that set it |
| executive summary | the claims of established findings, each with its id and citations - grounded by construction |
| established / awaiting review / not established | every finding with statement type, severity and its rule, confidence and its sum, verification, review, challenge, citations, unit issues |
| evidence | each document: Evidence Locker id, SHA-256, authority, integrity, the findings citing it |
| timeline | dates from grounded knowledge claims and established findings, in order |
| contradictions | CONTRADICTION findings with their review; the knowledge graph's conflicts |
| competing explanations, unknowns and next evidence | Phase 47's hypotheses; unresolved gaps; open explanations' leads or requests |
| recommendations | decisions awaiting review; which source is current for each contradiction; currencies to confirm; evidence to obtain; RECOMMENDATION findings |
| limitations | synthesis's limitations; findings awaiting a decision |
| path, narrative, trace | the plan with each step's why; synthesis's narrative with its grounding verdicts; every event |

"Established" = verified, needing no review or approved/modified (`counts_as_established`), and no
unit mismatch. Findings awaiting review or not established are listed and never raise the risk.

## Severity (`.agent/config/report.yaml`)

The highest rule a finding matches: UNIT_MISMATCH, contradiction or an overturning challenge HIGH; a
proposed risk or a contested challenge MEDIUM; otherwise LOW; a HIGH case lifts its findings to at
least MEDIUM, a CRITICAL one to HIGH. Every severity is printed with its rule.

Before a report, every HIGH or CRITICAL finding nobody has challenged is challenged with the
deterministic rule (Phase 48's deferred step; no model call), audited as `challenge.before_report`.

## The currency check (`reporting/units.py`)

Phase 41's known issue. The currencies a claim names (symbols, codes, words, lakh, crore) against the
ones its cited lines name: both name some and share none -> UNIT_MISMATCH, HIGH, not established, and
a recommendation to confirm it.

## Exports (`reporting/export.py`, `api/v1/reports.py`)

`GET /api/v1/missions/{id}/investigation-report` (JSON, no side effects) and
`.../investigation-report/export/{md|pdf|docx|json}`. An export writes a REPORTED event into the
custody of every cited evidence item (with the report id and hash) and an audit entry
`report.exported`; the response carries `X-Report-Hash`. Console: "Build the report" on the mission
page, with the four downloads.
