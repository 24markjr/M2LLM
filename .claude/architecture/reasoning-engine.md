# The reasoning engine

**Phases:** 13 (findings and evidence binding), 14 (evidence gap detection)
**Code:** `backend/app/intelligence/reasoning/engine.py`,
`backend/app/intelligence/evidence_gap/detector.py`

This is where observations become claims. It is the part of the system most able to lie, so
almost everything here exists to make lying structurally difficult rather than discouraged.

---

## The one idea

**A claim is only worth as much as the evidence that resolved behind it.**

The model proposes claims and cites locators. It does not decide whether those citations are
real, how confident the claim is, or what kind of claim it is. Those three things are computed
from whether the citations resolve against locators the tasks actually produced.

That inversion is the whole design. A model asked to self-report confidence will report
confidence; a model whose citations are checked cannot inflate one.

---

## The pipeline

```
observations
  -> compact to the observation budget       (context/manager.py)
  -> ask the model for candidate findings    (prompts/reasoning.md)
  -> relevance gate: does it answer the objective?   (prompts/relevance.md)
  -> bind citations to real locators         (EvidenceBinder)
  -> classify from what resolved             (Finding.classify)
  -> compute confidence                      (Confidence.compute)
  -> detect gaps in what is still missing    (evidence_gap/detector.py)
```

### Compaction preserves every locator

Long runs produce more observations than fit in a prompt. `compact()` summarises content and
drops structured payloads, but **`sources` is carried through untouched**. Losing a locator
would make every claim built on that observation unresolvable — a far worse outcome than a
longer prompt.

The budget is `agent.yaml: reasoning.observation_budget_tokens`, and it is an **input** budget.
This was a real defect: reasoning passed `models.yaml: roles.reasoning.max_tokens`, which caps
what the model may *generate*, so observations were squeezed five times tighter than intended.
Summarising is precisely what removes the dates and figures a contradiction rests on, and a
scenario with two planted contradictions returned nothing. A test now asserts the two numbers
cannot be conflated again.

### The relevance gate

Verification asks whether the evidence supports a claim. Nothing asked whether the claim
*answers the objective* — so a faithful restatement of a source passed every check and still
made the run wrong. Asked whether a report contradicted itself, the agent reported "the
approved completion date is 30 April 2026": true, correctly cited, and not an answer.

The gate is one model call for all candidates, judged against the objective, before binding.
Three properties matter:

- **It fails open.** If the call errors, findings pass through and verification still judges
  them on evidence. Dropping everything because a filter broke would produce the same output
  as an honest empty result and be indistinguishable from one.
- **Every drop is recorded** as `FINDING_DISCARDED` with its reason. A claim that vanished
  with no event would be indistinguishable from one the model never produced (invariant 4).
- **It has its own role** in `models.yaml`, with a small budget. It emits one short verdict per
  claim; a large budget buys only latency.

It is tuned to **keep when in doubt**. A borderline claim is still checked against its evidence
afterwards, so keeping one costs little — whereas dropping the only real finding makes the
whole investigation report nothing, which looks identical to a run where there was nothing to
find.

### The evidence binder

Every citation the model writes is matched against the locators the tasks actually produced.
A citation that cannot be matched is kept as **`UNRESOLVED`** — never dropped.

That is deliberate and it is the opposite of what a system optimising for looking good would
do. A dropped bad citation leaves a claim that appears fully supported. An `UNRESOLVED` one
says exactly what went wrong, caps the claim's confidence, and shows up in the report.

Locator parsing is anchored:

```python
_LOCATOR = re.compile(r"^\s*(?P<document>[^\s:]+?)\s*:\s*(?P<kind>[rpc]?)(?P<number>\d+)\b")
```

Models routinely quote the cited line after the reference — `report.txt:r7: Project Aurora
is a...`. Splitting on the last colon read the prose as the position and rejected every
citation, so an entire run came back `UNKNOWN` at zero confidence. Anchoring at the start and
ignoring the remainder accepts the reference the model meant without accepting one it did not
make. See BUG in `.claude/logs/bug-log.md`.

---

## Classification is recomputed, never accepted

The prompt asks the model to suggest `FACT`, `INFERENCE`, `HYPOTHESIS` or `UNKNOWN`. The
suggestion is advisory and **the stricter answer wins**.

| Class | Requires |
|---|---|
| `FACT` | every cited element resolves |
| `INFERENCE` | resolves, and combines two or more sources |
| `HYPOTHESIS` | partially supported |
| `UNKNOWN` | nothing resolved |

`agent.yaml: reasoning.classification_floors.fact_requires_full_resolution` enforces the first
row. A claim cannot be called a fact while resting on a citation nobody could find.

---

## Confidence is computed, and there is no other way to make one

```python
Confidence.compute(
    refs=refs,
    source_agreement=source_agreement(refs),
    classification=finding.classification,
)
```

`Confidence(value=0.96)` raises a `ValidationError`. There is no constructor that takes a bare
number, which means no code path anywhere in the system can assert a confidence it did not
derive. This is enforced in the type, not in a convention, because a convention is something a
future contributor can be unaware of.

It is built from four factors, each recorded on the finding so the number can be taken apart:

| Factor | Meaning |
|---|---|
| `resolution_rate` | share of citations that resolved |
| `evidence_strength` | how much independent evidence supports it |
| `source_agreement` | whether the sources agree |
| `classification_ceiling` | the cap the classification imposes |

`agent.yaml: reasoning.classification_floors.unresolved_citation_confidence_cap` (0.4) means a
claim with any unresolved citation cannot present as confident, whatever the other factors say.

---

## Gap detection names what is missing

A gap is not "more evidence needed" — that has failed at its job. It names the **specific
absent element**, so the replanning loop has something to act on:

```
gap_type:        MISSING_BASELINE
missing:         "approved baseline completion date"
element:         the claim element it belongs to
severity:        0.0-1.0, drives Phase 17 prioritisation
suggested_query: a concrete query, not a restatement
```

**The decision that a gap exists is deterministic.** It is made by comparing claim elements
against resolved evidence, before any model is asked anything. Only `suggested_query` is
phrased by a model, and only after the gap is already established. A model that could decide
whether a gap exists could also decide there wasn't one.

A resolved gap must name the task that resolved it — enforced by a validator on
`EvidenceGap` — otherwise the replanning loop cannot be audited.

---

## What this component never does

- **Never persists model deliberation** (invariant 3). `think: false` is sent to Ollama and the
  provider never reads the `thinking` field. The event log records that a call happened, its
  latency and its token counts — not what the model mulled over.
- **Never treats document text as instruction.** Every prompt states that observations are data
  under investigation. A document containing "ignore previous instructions" is content to be
  investigated.
- **Never invents a finding to avoid an empty result.** The prompt says so explicitly, and
  `aurora_no_contradiction` in the evaluation suite fails the build if it happens.

---

## Where this is measured

`.claude/testing/agent-evaluation.md`. The metrics that bear on this component are
`evidence_coverage`, `unsupported_claim_rate` (the hallucination proxy), and the negative-case
check that no positive scenario can detect.
