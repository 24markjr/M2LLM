# Regression testing

**Phase:** 20
**Code:** `backend/app/evaluation/report.py` — `compare()`, `RegressionResult`, `MetricDelta`
**Tolerances:** `_TOLERANCES` in `backend/app/cli.py`

A metric is only useful if a change in it means something. This is the machinery that decides
when a number moving is a regression, when it is noise, and when the two reports should not have
been compared at all.

```bash
python -m app.cli eval --suite all     # compares against the last committed report
```

---

## Reports that are not comparable are not compared

The first thing `compare()` does is refuse:

```python
if baseline.comparable_key != current.comparable_key:
    return RegressionResult(comparable=False, reason="...different model, prompt version or configuration...")
```

`comparable_key` is **model + prompt versions + config hash**.

A prompt change or a model swap makes the numbers describe a different system. Reporting that as
a regression would be wrong; reporting it as a pass would be worse, because it would launder an
untested change through a green check. Refusing is the only honest option, and the output says
so explicitly rather than silently skipping:

```
REGRESSION CHECK: skipped - the baseline was produced with a different model, prompt version
or configuration; the numbers describe different systems
```

This fires often during active development, and that is correct. It means the baseline must be
re-established after a prompt change — which is a real cost, and cheaper than a check that lies.

---

## Tolerances are wider than the noise

```python
_TOLERANCES = {
    "intent_accuracy": 0.05,          "plan_validity": 0.05,
    "dependency_correctness": 0.05,   "tool_selection_accuracy": 0.05,
    "evidence_coverage": 0.03,        "verification_success": 0.05,
    "replanning_success": 0.08,       "unsupported_claim_rate": 0.02,
    "task_efficiency": 0.20,          "latency_s": 30.0,
}
```

Every tolerance is deliberately wider than this suite's run-to-run variance. A local model is not
deterministic even at temperature 0 with a fixed seed — the same objective produces different
plans across runs — so a tolerance tighter than the jitter would report a regression on every
run and teach everyone to ignore the check. A check people ignore is worse than no check.

`replanning_success` gets the widest share-based tolerance because it depends on how many gaps a
run happened to detect, which varies most. `unsupported_claim_rate` gets the tightest, because it
is the hallucination proxy and the one number we least want drifting.

`LOWER_IS_BETTER = {unsupported_claim_rate, task_efficiency, latency_s}` — the direction of each
metric is declared, so a regression is computed rather than eyeballed.

---

## Unexplained improvements are also reported

```python
@property
def improved_beyond_tolerance(self) -> bool:
    """An unexplained jump usually means the measurement broke, not the agent improved."""
```

This is not pessimism, it is experience. A metric that leaps without an accompanying change is
most often a scorer returning a default, a scenario silently erroring into an empty result, or a
denominator becoming zero. `evidence_coverage` returning 1.0 because there were no findings is
exactly this shape.

A jump is surfaced for inspection. It does not fail the build — but it should be explained before
it is believed.

---

## What fails a build, and what merely regresses

| | Condition | Effect |
|---|---|---|
| **Build failure** | a negative case produced any findings | fails — with the claims listed |
| **Build failure** | a positive case with `expected_claims` produced **zero** findings | fails |
| **Build failure** | `unsupported_claim_rate > 0.15` | fails |
| **Regression** | any metric moved beyond tolerance in the wrong direction | reported, comparable reports only |
| **Flag** | any metric improved beyond tolerance | reported for inspection |

The three build failures are absolute: they do not need a baseline and they do not care about
tolerances. Inventing findings where none exist, and finding none where some were planted, are
both wrong in a way no comparison is needed to establish.

---

## Establishing a baseline

The latest report in `.agent/evals/reports/` for a suite is the baseline. Reports are committed,
so the baseline travels with the repo and a regression is attributable to a commit.

After any prompt or model change:

1. Run the suite. The check will skip — expected, the key changed.
2. Read the numbers and decide whether they are acceptable **on their own merits**, since there
   is nothing to compare against.
3. Commit the report. It is the new baseline.

Step 2 is the one that cannot be automated and the one most likely to be skipped.

---

## Verifying the harness detects real regressions

The acceptance criterion for Phase 20 is that a deliberately broken planner drops
`plan_validity` in the report. A harness nobody has ever seen fail is a harness that may not be
able to.

Two quick ways to prove it:

- constrain the planner prompt so it emits plans with cycles — `plan_validity` should fall
- point `verification_provider` at nothing so every check degrades — `verification_success`
  should move and `degraded` should appear on every finding

Neither is currently automated. See *Known gaps* in
`.claude/testing/agent-evaluation.md`.

---

## Known gaps

- **No CI integration.** Phase 23. `python scripts/export_openapi.py --check` is already
  CI-shaped; the eval suite needs a local model, so it will need a gate that skips cleanly
  without one rather than failing.
- **Fault injection is manual.** The two checks above should be scenarios, not instructions.
- **The current baseline is stale.** It predates the intent, plan-cap and observation-budget
  fixes, so the next run will correctly refuse to compare and a new baseline must be set.
