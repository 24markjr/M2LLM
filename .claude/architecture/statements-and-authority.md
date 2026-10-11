# Statement types and source authority (Phase 45)

What kind of statement each finding is, and how much weight each source carries. Decision record:
ADR-015.

## Statement types

| Type | Rule | Shown as |
|---|---|---|
| UNKNOWN | nothing it cites resolved | UNKNOWN |
| HYPOTHESIS | some citations did not resolve | HYPOTHESIS |
| SOURCE_CLAIM | every resolved citation in one document | SOURCE CLAIM |
| FACT | two or more documents, all resolved, claim supported or verified | FACT |
| INFERENCE | two or more documents, a step none of them states | INFERENCE |
| CONTRADICTION | two different values, both cited and resolved; comparison question or proposed as one | CONTRADICTION, with each side's authority |
| RISK / RECOMMENDATION / OBSERVATION | proposed by the model over a FACT, SOURCE_CLAIM or INFERENCE basis | "RISK on SOURCE CLAIM" |

- **Where:** `backend/app/intelligence/reasoning/statements.py` (`type_statement`,
  `type_statements`), called by `orchestration/mission.py` after replanning, when the findings are
  final. Knowledge-graph conflicts (BUG-031) arrive with `proposed_type="CONTRADICTION"`.
- **Fields on `Finding`:** `statement_type`, `statement_basis` (what the evidence supports),
  `proposed_type` (the model's word). Stored in `findings.statement_type`.
- **Invariant:** `Finding._no_single_source_fact` - a FACT type or basis needs two resolved documents.
- **Shown:** the report's finding lines (`synthesis/engine.py` `statement_text`, `_finding_line`), the
  console's finding badge (`frontend/src/components/statements.ts`), with the model's proposal in the
  badge's help text.
- **Measured:** `vega_authority_conflict` (CONTRADICTION, both sides cited) and
  `vega_start_corroborated` (FACT when one finding cites both documents; SOURCE_CLAIMs otherwise).

## Source authority

- **Tiers** (`.agent/config/authority.yaml`, highest first): APPROVED, OFFICIAL, REPORT, DRAFT,
  CORRESPONDENCE, UNASSESSED (neutral). Each has a label and the weight Phase 46 will record.
- **Set at intake** (`evidence/service.py` `intake`, `register`) by ordered rules over the file name;
  `authority_reason` says which word matched. Items filed before Phase 45 are assessed by the same
  rules on the next listing, recorded as METADATA_CHANGED.
- **Changed by a person:** `PATCH /api/v1/evidence/{id}` with `authority` and `authority_reason`, on the
  item's page; an unknown tier is refused (422 `UNKNOWN_AUTHORITY_TIER`). Recorded in custody.
- **Into a mission:** the API reads each admitted item's tier (`authority_of`) and fixes it on the
  record (`MissionDetail.authority`); the CLI and evaluation fall back to the rules
  (`authority_map`). Synthesis prints both sides' tiers on every CONTRADICTION.
- **Never decides.** Nothing ranks or drops a finding by authority (ADR-015).
- **No config file:** every source is UNASSESSED and missions run as before.
