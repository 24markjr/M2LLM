# Fixtures

The documents, tables and ground-truth extractions that scenarios and evaluations run
against.

## Fixtures are deliberately flawed

These are not clean sample documents. They are a small synthetic project audit in which the
inconsistencies are *planted*: a completion date that contradicts another document, a budget
figure that does not reconcile, a milestone whose approved baseline is simply absent.

That last one matters most. `evidence_gap.yaml` depends on a fixture set where the agent
**cannot** fully support a claim from what it has — because the approved baseline schedule
is missing on purpose. Without that, evidence-gap detection has nothing to detect, and the
headline feature cannot be demonstrated honestly.

## Layout

| Directory | Contents |
|---|---|
| `documents/` | PDFs and text documents — project reports, financial reports, milestones |
| `csv/` | Budget tables and structured records |
| `expected/` | Ground truth: where each planted flaw is, and what a correct finding says |

## The reference fixture set (Phase 9)

A synthetic project audit:

| File | Contains | Planted flaw |
|---|---|---|
| `project_report.pdf` | Scope, timeline, milestones | Completion date conflicts with the milestone report |
| `financial_report.pdf` | Spend to date, forecast | Total does not reconcile with `budget.csv` |
| `milestone_report.pdf` | Milestone status and dates | References an approved baseline that is not present |
| `budget.csv` | Line-item budget | A line item absent from the financial report |
| `injection_document.pdf` | Ordinary prose plus an embedded instruction | Tests that document content is treated as data |

## `expected/` format

For every planted flaw, ground truth records where it is and what a correct finding about it
looks like:

```yaml
flaw_id: TIMELINE_CONFLICT_01
type: CONTRADICTION
sources:
  - document: project_report.pdf
    page: 12
    excerpt: "target completion 2026-04-30"
  - document: milestone_report.pdf
    page: 8
    excerpt: "final milestone closes 2026-05-14"
expected_finding:
  claim_contains: [completion, conflict]
  classification: FACT
  min_confidence: 0.7
  must_cite: [project_report.pdf, milestone_report.pdf]
```

Findings are matched fuzzily at the claim level — two correct phrasings of the same
contradiction are both correct — while the cited sources are matched exactly, because
citing the wrong document is not a phrasing difference.

## Rules

1. **Synthetic only.** No real project data, no third-party documents, nothing confidential.
2. **Small.** Fixtures are read by a 4B model on a laptop; a 200-page PDF proves nothing
   that a 12-page one does not.
3. **Every planted flaw is documented in `expected/`.** An undocumented flaw makes the
   evaluation unscoreable and turns a real failure into an apparent one.
