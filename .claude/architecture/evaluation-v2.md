# Evaluation v2 and the quality summary (Phase 54)

Code: `backend/app/evaluation/quality.py`, `report.py` (`CategorySummary`, `EvalReport.categories`),
`runner.py` (`ScenarioExpectation.category`). API: `GET /api/v1/evaluation/quality`. UI: the
Evaluation page, `frontend/src/components/QualityPanel.tsx`, `quality.ts`.

## Categories

Every scenario in `.agent/evals/datasets/` names one `category`. The agent report groups its scenarios
by category and gives each group its own aggregate metrics, its negative pass rate and its
claims-found rate, so a figure is never read without its dataset. A rate a group cannot have (claims
found in a group with no positive scenario) is absent, not zero. A report written before categories
existed still reads; its scenarios fall under `uncategorised`.

| Category | Scenarios |
|---|---|
| temporal_contradiction | aurora_contradiction, aurora_pdf_timeline, aurora_timeline_only, helix_schedule_contradiction, shipment_arrival_conflict |
| negative | aurora_no_contradiction, helix_budget_consistent, orion_meeting_consistent, shipment_9012_consistent |
| financial | helix_budget_unapproved, orion_ledger_overrun |
| evidence_gap | helix_evidence_gap |
| noisy_ocr | orion_scanned_delivery |
| injection | injection_document |
| conflicting_authority | vega_authority_conflict |
| corroboration | vega_start_corroborated |
| hypotheses | lyra_outage_undetermined |
| cyber | cyber_encoded_powershell, cyber_lateral_movement, cyber_admin_benign |

Not built from the plan's list: *forged evidence* is covered by the Evidence Locker's integrity tests
(a hash comparison, not a model behaviour) and *entity ambiguity* has no scenario yet; *challenges*
are their own benchmark (`eval-challenge`), reported as a component below.

## The quality figure

An unweighted mean of named components, each in 0..1, each computed from the newest committed report
it names, each with its formula and dataset served alongside it. The formula is shown on the page,
and the page writes the mean out ("mean(0.983, 1.000, ...) = 0.912").

| Component | From | Formula |
|---|---|---|
| grounding | agent baseline | 1 - unsupported_claim_rate |
| verification | agent baseline | verification_success |
| negatives | agent baseline | negative scenarios with no finding / negative scenarios |
| claims found | agent baseline | mean share of planted claims found, positive scenarios |
| open questions | agent baseline | 1 - premature_conclusion_rate |
| challenge | challenge benchmark | catch rate x (1 - false alarm rate) |
| ATT&CK | ATT&CK benchmark | F1 of technique precision and recall |
| injection | trust benchmark | injection detection rate |

Unweighted because any weighting is a judgement the reader cannot check; the components are listed so
a reader who disagrees can recompute. Tamper detection is left out: it is correct by construction
and would only raise the mean. A missing report is listed under `missing` with the command that
produces it, and the mean is taken over what exists.

## The trend

Agent quality (the five agent components) for every committed agent report, oldest first. Points are
grouped by the report's `comparable_key` (model, prompts, config); the chart never draws a line
across a change of configuration. The benchmarks have one report each and are not trended.

## Raw metrics

The previous Evaluation page (every raw metric, every committed report, direction of good) is kept
under a "Technical" checkbox below the summary.

## Model-free benchmarks in CI

`check_eval_reports.py`, `check_trust_reports.py`, `check_challenge_report.py` and
`check_attack_report.py` re-run or re-check the deterministic benchmarks on every push;
`check_documented_metrics.py` holds the README and contribution figures to the newest baseline.

## Changes the baseline forced

The first Phase 54 baseline (`20261012T074106`) failed one threshold: `cyber_admin_benign`, a negative
scenario, produced two findings in all three runs - a completed backup and an administrator's package
upgrade, both true and both verified. Two deterministic changes followed:

- **No detection, no finding (BUG-038).** When the objective asks about an attack
  (`asks_about_attack`: malicious, compromise, intrusion, lateral movement, ...) and the documents are
  security logs in which no ATT&CK rule flagged any event (`quiet_logs`), reasoning discards every
  candidate with the reason "no detection rule flagged any event: it describes ordinary activity".
  The cost is stated, not hidden: an attack that no rule covers is then reported as nothing. The
  held-out ATT&CK fixture (recall 0.400) measures how much that can be.
- **Addresses are specifics (BUG-039).** The live check after that change showed the verifier accept
  "On server 10.0.0.12, svc_admin ran PSEXESVC.exe" citing a line that reads `host=SRV-DB` - the
  address was the logon's source, on another line. `ungrounded_specifics` now treats an IPv4 address
  like a date or a figure: a claim cannot state one that its cited lines do not contain.

The knowledge tool's cyber items were narrowed at the same time to decoded commands and relations
whose lines an ATT&CK rule mapped, so benign activity is not handed to reasoning as if it mattered.

## Measured

See the Phase 54 entry in `.claude/implementation/v2-plan-phases-43-55.md` and the newest
`.agent/evals/reports/*-all.md`.
