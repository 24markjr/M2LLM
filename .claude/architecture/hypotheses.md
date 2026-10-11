# Competing explanations, knowledge gaps and next best evidence (Phase 47)

## When it runs

Only when the objective asks for an explanation - why, cause, explain, what happened, how did,
responsible for, led to, root cause (`hypotheses/engine.py` `wants_explanation`). A comparison ("do
these documents contradict each other?") gets none and costs nothing. Switch: `agent.yaml`
`hypotheses.enabled`.

## What it does

After the findings are final (statement types and confidence set), so it can never change one:

1. **Propose** (one model call, prompt `hypotheses.md` v1, role `hypotheses`): two to four competing
   explanations, each with the evidence that would decide it and a search for it. No ranking, no
   probabilities. Fewer than two is not a competition: the step reports why and stops.
2. **Test** (one model call, `hypothesis_test.md` v1), only when there are verified findings: which
   of them SUPPORT or CONTRADICT each explanation. Unverified findings, unknown ids and repeated pairs
   are ignored.
3. **Rank, computed** (`rank`): support = sum of the confidence of the verified findings for it;
   against = the same against it. REJECTED when against - support >= `rejected_min` (0.5).
   SUPPORTED only when its net >= `supported_min` (0.5) *and* it leads the next by
   `supported_margin` (0.3). Everything else stays OPEN. Determined = exactly one SUPPORTED.
4. **Next best evidence** for each OPEN explanation (`search_leads`): the document search tool's
   lexical rule over the run's documents with the explanation's query, at least half its words on a
   line. Lines found -> SEARCH with them as leads (not findings: nothing has checked them). None ->
   ANALYST_REQUEST naming what a person must provide.

The leads do not re-enter the replanning loop. A lead becomes evidence through an investigation of
its own; the console's "investigate these lines" opens New Mission prefilled with the explanation,
the documents the leads are in, and the case.

## Where it shows

- `MissionResult.hypotheses` (`HypothesisSet`), `GET /api/v1/missions/{id}/hypotheses`, the replay
  snapshot, the `HYPOTHESES_EVALUATED` event.
- Console: a "Competing explanations" panel after the findings - status, support computed (for,
  against), the findings on each side, what would decide it, next evidence with a link to test it
  (SEARCH) or to add evidence (ANALYST_REQUEST).
- The report gains a hypotheses section in Phase 51.

## Measured

- `lyra_outage_undetermined` (an outage three minutes after a configuration change and one after a
  power dip; the UPS log that would decide it not attached). One live run, 2026-10-11: undetermined,
  four explanations open, three with leads in the documents (one the line saying the UPS log is not
  attached), one an analyst request; no premature conclusion. That run produced no verified finding,
  so the test call was skipped (one model call).
- The evaluation reports `premature_conclusion_rate` over scenarios with `expect_open_hypotheses`, and
  a premature conclusion fails the build.
