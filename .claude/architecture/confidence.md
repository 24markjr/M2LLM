# Confidence, decomposed and explained (Phase 46)

## Why it changed

Measured on 2026-10-11 over the 26 findings in the recorded runs: 22 sat at exactly 0.85, for two
unrelated reasons (one document scored 0.85 "agreement"; an INFERENCE was capped at 0.85), and
verification did not move confidence at all - the three findings the verifier rejected kept 0.85.

## The formula

```
value = resolution x (sum of weight x factor) - penalties, capped
```

| Factor | Value | Weight (`.agent/config/confidence.yaml`) |
|---|---|---|
| resolution | resolved / cited citations | gate (multiplier) |
| evidence_strength | line citation 1.0, page citation 0.7, averaged | 0.20 |
| independence | 1 document 0.6, 2 documents 0.85, 3+ 1.0 | 0.25 |
| authority | mean tier weight of the cited documents (Phase 45) | 0.10 |
| verification | SUPPORTED 1.0, PARTIAL 0.6, INCONCLUSIVE/unverified 0.4, rejected 0; x0.8 if degraded | 0.35 |
| temporal_consistency | share of the claim's dates and figures on its cited lines; not counted without the text | 0.10 |
| disputed (penalty) | -0.15 when a cited line is one side of a CONTRADICTION finding | - |

Weights are normalised over the factors assessed, so the contributions add up to the weighted sum.
The cap is the classification ceiling, or a verdict cap when the verifier rejected the claim
(UNSUPPORTED 0.30, CONTRADICTED 0.10); `cap_reason` says which.

Entity resolution, named in the plan, is not a factor: nothing resolves entities across documents
yet, and a factor fixed at 1.0 would be decoration.

## Where

- `backend/app/intelligence/confidence.py`: `assess`, `rescore` (all findings, with the disputed
  penalty), `why` (sentences whose numbers add up, and what kept it lower, largest first).
- `Confidence.from_factors` (`schemas/finding.py`): still no bare number; `factors`, `weighted`,
  `penalty`, `cap_reason` are stored with the value. `explain()` prints the sum.
- Applied once in `orchestration/mission.py`, after replanning and statement typing. The replanning
  loop's diminishing-returns stop reads the simpler value it always did, so the loop and the
  evaluation baseline are unchanged.
- A verified finding from two or more documents (a FACT basis, Phase 45) whose classification was
  still INFERENCE - verified without being decomposed - is raised to FACT in that final pass; without
  it, the 0.85 INFERENCE cap ranked it below a one-document claim.

## Re-measured (offline, the same 26 recorded findings, no model)

| Verdict, documents | Before | After |
|---|---|---|
| supported, 2 documents (8) | 0.85 | 0.93 |
| supported, 1 document (11) | 0.85 | 0.81-0.89 |
| rejected, 1-2 documents (3) | 0.85 | 0.30 (capped) |
| nothing resolved (4) | 0.00 | 0.00 |

## The evidence chain

`GET /api/v1/missions/{run_id}/findings/{finding_id}/chain` (`app/api/chain.py`): claim, each
citation (Evidence Locker item, authority, the text verification read, what the knowledge pass
extracted from that line), how reasoning proposed it and how it was ruled, each verifier's verdict,
and the conclusion with its "why". Built from what the run holds; nothing is recomputed or asked of a
model. `GET .../findings` also returns `why` per finding.

Console: the finding card's evidence panel shows "Why 0.89?" - the sum, a factor table and what held
it down - from the stored factors (so a replay shows it too), and "show the evidence chain" fetches
the chain on a live run, with links to the Evidence Locker item and the knowledge graph.
