# Verification

**Phase:** 15
**Code:** `backend/app/integrations/verification.py`
**Integration contract:** `.claude/integrations/member-4-verification.md` — *not yet written;
indexed in `.claude/integrations/README.md` as expected. The contract this side relies on is
the `VerificationProvider` protocol in `backend/app/integrations/verification.py`.*

Verification asks one question about a finding: **does the evidence actually support this
claim?** It is the check that stands between a plausible sentence and a reported finding.

---

## Why it sits outside the plan

Verification is a **pipeline stage, not a planned task.** The planner never schedules it, and
`Operation.VERIFY_FINDINGS` is classified in `SUPPORTING_OPERATIONS` so the plan is not required
to contain a task for it.

That matters for a reason worth stating plainly: a task the planner scheduled runs inside the
same process that produced the findings, using the same context. A check that shares the
reasoning it is checking is not independent, and an agent grading its own work with its own
notes in front of it will agree with itself.

So verification runs on **every** finding, outside the plan, and cannot be omitted by a planner
that had a bad run.

## It does not see the reasoning trail

`agent.yaml: verification.independent_context: true`.

The verifier receives the claim and the evidence. It does not receive the reasoning that
produced the claim, the other findings, or the objective's framing. It is asked to check a
statement against sources, not to agree with a conclusion.

`models.yaml: roles.verification` has a deliberately small budget (600 tokens). The job is a
verdict plus specific issues, not an essay.

---

## The verdict vocabulary

```python
SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED | INCONCLUSIVE
```

Two distinctions in here are load-bearing:

**`UNSUPPORTED` vs `CONTRADICTED`.** An unsupported claim is *unproven* — more evidence might
establish it, so the replanning loop inserts a task to go and look. A contradicted claim is
*wrong* — the evidence says the opposite, and no amount of further evidence rescues it, so the
loop deliberately does **not** retry it. Collapsing these two into "failed" would make the agent
spend its iteration budget working hard on claims it had already disproved.

**`INCONCLUSIVE` is never treated as a pass.** It means the check could not be performed. A
system that counted "could not check" as "checked" would report its blind spots as successes.

## Issues, not just a status

A bare status tells the replanning loop nothing it can act on. Every verdict carries issues:

```python
issue_type: NO_EVIDENCE | UNRESOLVED_CITATION | EVIDENCE_MISMATCH | OVERSTATED_CLAIM
          | SOURCE_CONFLICT | UNIT_MISMATCH | DATE_AMBIGUITY | ARITHMETIC_ERROR
element:      which part of the claim
description:  what specifically is wrong
severity:     LOW | MEDIUM | HIGH
```

`element` plus `issue_type` is what lets gap detection name a missing element and the planner
insert a task that could plausibly find it. Without them the loop could only retry blindly.

---

## Degradation is declared, never hidden

Member 4 owns an external verification service. `settings.verification_provider` selects
between it and `BaselineVerifier`, which performs a weaker structural check locally.

When the external verifier is unavailable the system falls back — and **says so**:

```python
VerificationResult(
    status=...,
    degraded=True,
    degraded_reason="the verification service was unreachable",
    verifier="baseline",
)
```

`degraded` propagates to the API, the report and the UI, where Mission Control renders a
`DEGRADED CHECK` badge on the finding.

A silent fallback would be the most damaging failure this system could have. Every finding
would still carry a verification state, the report would still look complete, and the check
behind it would be weaker than anyone reading it believed. A check that quietly got weaker is
worse than no check, because no check is visible.

---

## What happens to each verdict

| Verdict | Effect |
|---|---|
| `SUPPORTED` | counted as verified; contributes to overall confidence |
| `PARTIALLY_SUPPORTED` | reported as uncertain, with its issues |
| `UNSUPPORTED` | gap detection runs; the replanning loop may insert a task |
| `CONTRADICTED` | reported as rejected; **not** retried |
| `INCONCLUSIVE` | reported as uncertain; never counted as verified |

Rejected findings appear in the report. They are not deleted — a claim the sources refute is a
result of the investigation, and removing it would leave the report looking cleaner than the
run actually was.

---

## The four implementations

Selected with `VERIFICATION_PROVIDER`. All four see the same `VerificationRequest`: the claim and
the cited text, never the reasoning.

| Provider | What it is | Model call |
|---|---|---|
| `baseline` (default) | Member 1's model-based check, `verification.md` prompt | yes |
| `remote` | Adapter for a verification service at `VERIFICATION_BASE_URL`; degrades to baseline | via service |
| `lexical` | **Member 4's verifier, ported (Phase 26).** TF-IDF relevance, plus a contradiction when claim and evidence share an identifying number and disagree on a date or time | no |
| `composite` | `baseline` and `lexical` together, with the rules below | yes |

**What the text is.** Since BUG-015 (Phase 25), the evidence text for each locator is the cited
line, or the matched lines of a cited PDF page. Before that, every verifier received the tool's
summary ("11 date(s)"), so verdicts before 2026-10-03 were made against the wrong text.

**Mapping Member 4's vocabulary.** `INSUFFICIENT_EVIDENCE` becomes `INCONCLUSIVE` with a
`NO_EVIDENCE` issue, and is never a pass. `CONTRADICTED` carries a `SOURCE_CONFLICT` issue naming
the conflicting locator and the reason ("dates 2026-09-20 vs 2026-09-14 on shared id 4821").

**Composite rules**, in order:

1. Lexical `CONTRADICTED` and the model not → `CONTRADICTED`. The lexical rule is high precision:
   it needs a shared identifier, disjoint dates or times, and relevance ≥ 0.5.
2. The model `INCONCLUSIVE` and lexical decisive → lexical's verdict, `degraded=True`, with the
   reason. A weaker check being used is never silent.
3. Otherwise the model's verdict. A lexical `SUPPORTED` never overrides a model rejection, because
   word overlap is not meaning.

Both opinions are recorded on the result (`opinions`) and in the `FINDING_VERIFIED` /
`FINDING_REJECTED` payload, so disagreement is measurable. Whether `composite` becomes the default
is decided by Exp-004 (Phase 34), not by argument.

---

## What this component never does

- **Never rescues a claim.** It has no authority to rewrite, soften or reclassify a finding. It
  reports; the reasoning engine and the replanning loop decide what follows.
- **Never sets confidence directly.** Confidence is computed from evidence resolution
  (`.claude/architecture/reasoning-engine.md`). Verification constrains what is *reported*, not
  the arithmetic.
- **Never fails a run.** An unreachable verifier degrades; it does not abort. An investigation
  that reached findings should report them with an honest caveat rather than nothing at all.

---

## Where this is measured

`verification_success` in `.claude/testing/agent-evaluation.md` — the share of candidate
findings that survive independent verification.

The number is expected to be well under 1.0, and a suspiciously high one is a signal to
investigate the verifier rather than to celebrate. A verifier that approves everything scores
perfectly and is worthless.
