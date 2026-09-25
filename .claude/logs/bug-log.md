# Bug Log

Defects found during development, what caused them, and how they were fixed.
A bug is recorded here even when the fix is trivial — the pattern matters more than the
individual defect.

---

## BUG-001 — Healthcheck crashed rendering its own report on the Windows console

**Found:** 2026-09-23, Phase 0
**Severity:** Low (tooling only) — but it masked the result it was meant to report
**Status:** Fixed

**Symptom**

`python scripts/healthcheck.py` printed the first two check rows, then died:

```
UnicodeEncodeError: 'charmap' codec can't encode character '→'
```

**Cause**

The report renderer used `→` for hints and `—` in two detail strings. The Windows console
defaults to code page 1252, which has no mapping for either. The failure happened *while
printing a FAIL row*, so the first real failure the script detected was also the first thing
that broke it.

**Fix**

Operator-facing output is ASCII-only. `→` became `->`, em dashes became hyphens. Non-ASCII
remains fine in comments and docstrings, which are never written to the console.

**Lesson recorded**

Anything printed to a terminal on Windows stays in ASCII unless the code page is explicitly
set. This applies to the CLI entry point (Phase 9) and the evaluation report renderer
(Phase 20), both of which will print status output.

---

## BUG-002 — `extract_json` returned a fragment for JSON array responses

**Found:** 2026-09-23, Phase 4 (by `test_extract_json_tolerates_real_model_output`)
**Severity:** High — would have produced silently wrong data, not an error
**Status:** Fixed

**Symptom**

`extract_json('[{"name": "a"}]')` returned `{"name": "a"}` instead of the array.

**Cause**

The balanced-delimiter scan tried `{`/`}` before `[`/`]`. In an array of objects the first
`{` appears at index 1, so the scan locked onto the first element and returned it.

**Why it mattered more than it looks**

The result is still valid JSON, so nothing downstream would have raised. A reasoning engine
asked for a list of candidate findings would have received the first one and reported
exactly one finding, with no error anywhere. A test that only checked "did we get a valid
object back" would have passed.

**Fix**

Start the scan from whichever of `{` or `[` appears first in the text.

**Lesson recorded**

Parsers that recover from malformed input need tests for *correct* input that is merely
unusual. The dangerous failure was not a crash — it was a plausible, valid, wrong answer.

---

## BUG-003 — Empty model responses: qwen3 spends its token budget on deliberation

**Found:** 2026-09-23, Phase 4 (live-model acceptance tests)
**Severity:** High — every structured call against the default model failed
**Status:** Fixed

**Symptom**

Every live-model test failed. `CompletionResponse.text` was empty, and
`StructuredOutputError` was raised after exhausting all repair attempts.

**Cause**

`qwen3:4b` is a reasoning model. Ollama returns the deliberation in a separate `thinking`
field and the answer in `response`. With a modest `num_predict`, deliberation consumed the
entire budget:

```
response = ''   thinking = 'Hmm, the user just asked...'   done_reason = 'length'
```

The repair loop then dutifully retried three times against a model that was always going to
run out of tokens before answering — the loop behaved correctly and could not help.

**Fix**

Send `think: false` on every request, configurable per role via `models.yaml`. The provider
reads only `response` and never reads `thinking`.

**The part worth keeping**

`thinking` is model deliberation by definition — precisely what invariant #3 keeps out of
the system. Never reading it is the first line of defence; event-bus redaction is the
second. `test_reasoning_deliberation_never_enters_the_response` holds it.

**Lesson recorded**

A repair loop cannot fix a budget problem. When every attempt fails identically, suspect the
request rather than the response — and check the provider's raw payload rather than only the
field the abstraction exposes.

---

## BUG-004 — Every Aurora citation came back UNRESOLVED

**Found:** 2026-09-24, Phase 13 (surfaced by the first live Aurora run)
**Severity:** High — every finding was classified `UNKNOWN` at zero confidence
**Status:** Fixed

**Symptom**

A live run produced findings whose citations all resolved to `UNRESOLVED`, so every claim was
capped at `UNKNOWN` and the report carried no confidence at all. The locators the model wrote
looked correct by eye.

**Cause**

The model appends the quoted line after the reference:

```
report.txt:r7: Project Aurora is a data platform...
```

The parser used `rpartition(":")`, which split on the **last** colon and read the quoted prose as
the row position. `int("...")` failed, the locator was rejected, and the whole citation was
discarded.

**Fix**

An anchored regex that reads the reference at the start and ignores whatever follows:

```python
_LOCATOR = re.compile(r"^\s*(?P<document>[^\s:]+?)\s*:\s*(?P<kind>[rpc]?)(?P<number>\d+)\b")
```

This accepts the reference the model actually meant without accepting one it did not make.

**Pattern**

A parser written against the format we asked for, tested only against the format we asked for.
The model complied *and added something*, which is the common case, not the edge case.

---

## BUG-005 — The agent confabulated on a scenario with nothing to find

**Found:** 2026-09-24, Phase 20 (first evaluation run)
**Severity:** High — the failure mode the whole project exists to avoid
**Status:** Fixed, with residual variance

**Symptom**

`aurora_no_contradiction` supplies one internally consistent document and asks whether it
contradicts itself. The correct answer is no findings. The agent produced **8**.

Every one of them passed verification, because every one was a true restatement of the document
with a citation that resolved.

**Cause**

Two layers, neither at fault on its own:

1. The reasoning prompt never said that returning nothing was acceptable. A model asked for
   findings produces findings.
2. **Nothing in the pipeline asked whether a claim answered the objective.** Verification checks
   whether the evidence supports the claim — and for a restatement, it does. There was no stage
   between "supported" and "reported".

**Fix**

Reasoning prompt v2 states explicitly that an empty result is a correct answer, plus a new
**relevance gate** (`prompts/relevance.md`, `ReasoningEngine._filter_irrelevant`) that judges
each candidate against the objective before binding. It fails open on any provider error and
emits `FINDING_DISCARDED` with a reason for every drop.

Measured: 8 -> 1 confabulated claim.

**Residual**

One restatement still leaks intermittently at `qwen3:4b`. The evaluation suite fails the build on
it rather than tolerating it.

**Pattern**

No positive scenario could have found this. An agent that invents findings scores 1.0 on
coverage, 1.0 on verification and 0.0 on unsupported claims — a perfect score for being exactly
wrong. Negative cases are the only test that can detect it.

---

## BUG-006 — Input and output token budgets were the same number

**Found:** 2026-09-24, Phase 13 (surfaced by the Phase 19 smoke run)
**Severity:** High — a scenario with two planted contradictions returned zero findings
**Status:** Fixed

**Symptom**

A live run over HTTP against all three Aurora fixtures produced **no findings at all**, on the
reference scenario where two contradictions are deliberately planted and documented.

**Cause**

`compact()` bounds how many tokens of observations enter the reasoning prompt. Its own default is
6000. Reasoning passed:

```python
budget = get_models_config().params_for("reasoning").max_tokens   # 1200
bounded = compact(observations, token_budget=budget)
```

`max_tokens` is the cap on what the model may **generate**. So observations were squeezed five
times tighter than intended — and summarising is precisely what strips the dates and figures a
contradiction rests on. The evidence survived as locators and lost its content.

Worst exactly when it mattered most: a large plan produces many observations, so the more work
the agent did, the less it could see.

**Fix**

`agent.yaml: reasoning.observation_budget_tokens` (6000), carried on `AgentBounds`. A test asserts
the observation budget exceeds the generation budget and never drops below `compact()`'s own
default.

**Pattern**

Two different quantities sharing a plausible name. `max_tokens` reads like "the token budget", and
there are two.

---

## BUG-007 — Mission list order varied between identical requests

**Found:** 2026-09-24, Phase 19 (found by a test)
**Severity:** Low
**Status:** Fixed

**Symptom**

`GET /api/v1/missions` returned two missions in a different order on different calls, with no
change in between.

**Cause**

Sorted by `created_at`. Two missions created in the same millisecond tie, and Python's sort is
stable with respect to dictionary order, which is insertion order — but the reverse sort made the
tie resolve unpredictably relative to what a reader expected.

**Fix**

`MissionRecord` carries a monotonic `sequence` from `itertools.count()`, and the listing sorts on
that.

**Pattern**

Timestamps are not identities. Any list a user reads top-down needs a total order, not a mostly-
total one.

---

## BUG-008 — mypy called live code dead because `finished` was a property

**Found:** 2026-09-24, Phase 19
**Severity:** Low (type checking only) — but it was pointing at something real
**Status:** Fixed

**Symptom**

`mypy --strict` reported three `unreachable` errors inside the SSE loop, at the checks that
decide when a finished run should close its stream.

**Cause**

`MissionRecord.finished` was a property. mypy narrows a property's truthiness, so after the early
`if record.finished: return` it treated the value as permanently `False` and every later check as
dead code.

The narrowing is wrong here for a real reason: the run finishes **while** the stream is reading
it, in another task.

**Fix**

`is_finished()` — a method. Method calls are not narrowed, and it reads better for mutable state.

**Pattern**

A property implies a stable attribute. State that changes under the caller should look like a
question being asked, not a field being read.

---

## BUG-009 — One word made an objective unplannable

**Found:** 2026-09-24, Phase 7
**Severity:** High — the reference objective could not be planned at all
**Status:** Fixed

**Symptom**

Every plan for the Aurora contradiction objective failed with `UNCOVERED_OPERATION`, three
re-prompts running, and the run failed cleanly having produced nothing. The log showed:

```
planner_invented_task_type proposed=detect_contradictions
```

**Cause**

The closed vocabulary has `detect_inconsistencies`. The model proposed `detect_contradictions`
persistently. The task was dropped as an invented type, which left the operation uncovered, which
failed the plan.

So an objective *about finding contradictions* could not be planned because of one synonym.

**Fix**

`_TASK_TYPE_SYNONYMS` in the planner — small and explicit, mirroring `_SYNONYMS` in the intent
engine and for the same stated reason: never fuzzy, because a fuzzy matcher reintroduces the
silent nearest-match problem a closed vocabulary exists to prevent.

**Pattern**

A closed vocabulary needs an explicit synonym layer at every boundary a model writes into, not
just the first one anybody thought of.

---

## BUG-010 — The intent demanded 17 operations, so no plan could cover them

**Found:** 2026-09-24, Phases 6 and 7
**Severity:** High — the root of the zero-findings chain
**Status:** Fixed

**Symptom**

With a 10-task plan cap, every plan failed `UNCOVERED_OPERATION`. The intent for one objective
required **17** operations; the evaluation dataset expects 6. `intent_accuracy` sat at 0.459 and
had been reporting this all along.

**Cause**

Two independent causes:

1. **`RequiredOperation.optional` was dead.** The field existed and `Intent.mandatory_operations`
   filtered on it, but **nothing ever set it**. So every operation became one the plan was
   required to contain — including `verify_findings` and `summarize`, which are *pipeline stages*
   no planner schedules, and `normalize_dates`, which happens inside extraction.
2. **The intent prompt asked which operations were "needed"** with no pressure toward minimality.
   A small model shown a 17-item vocabulary picks most of it.

**Fix**

`SUPPORTING_OPERATIONS` in `schemas/intent.py` classifies pipeline-inherent operations in code —
which operations are inherent is a fact about this architecture, not a per-run judgement for a
model. Plus intent prompt v2: ask for the fewest, state that three to six is normal, and name the
specific over-reach measured here.

Measured: 17 -> 7 operations, 16 -> 7 tasks, 0 -> 4 findings.

**Pattern**

A dead field is worse than a missing one. `mandatory_operations` read as though the distinction
was being enforced, and the code that would have set it was never written.

---

## BUG-011 — `eval` crashed before it could compare against a baseline

**Found:** 2026-09-24, Phase 20
**Severity:** Medium — the regression check never ran
**Status:** Fixed

**Symptom**

```
NameError: name '_TOLERANCES' is not defined
```

Every `python -m app.cli eval` run died at the regression comparison, *after* printing its
results — so the metrics looked fine and the check silently never happened.

**Cause**

`_TOLERANCES` was defined at the bottom of `cli.py`, **below** `if __name__ == "__main__":
sys.exit(main())`. Under `python -m app.cli`, `main()` runs during module execution, so the
assignment below it had not been reached.

**Fix**

Moved above the entry point.

**Pattern**

Module-level code after the `__main__` guard is unreachable when the module *is* the entry point.
It looked like ordinary top-level configuration.

---

## BUG-012 — My own prompt example taught the model to write uncheckable citations

**Found:** 2026-09-25, Phase 13 (while fixing BUG-005)
**Severity:** Medium — the only surviving contradiction was unsupportable
**Status:** Fixed

**Symptom**

After the comparative rule landed, the one finding that survived on the contradiction scenario was:

```
The dates conflict: Document A gives 30 April, document B gives 14 May
```

Its citations did not resolve, so `unsupported_claim_rate` went from 0.000 to **0.333** — over the
0.15 ceiling — and `evidence_coverage` fell to 0.667.

**Cause**

That sentence is **verbatim from `reasoning.md` v2**, where I had written it as an illustration of
how to phrase a contradiction:

> state the conflict in a single claim and cite both sides: "Document A gives 30 April, document B
> gives 14 May" is one finding, not two

The model copied the example including the placeholder document names, so the claim referred to
documents that do not exist and nothing could be resolved against them.

**Fix**

Prompt v3: the example now uses real filenames, and the rule says explicitly never to write
"Document A" or "the first document", because a placeholder cannot be checked against anything.

**Pattern**

An example in a prompt is not illustration, it is a template. A small model will copy its surface
form, placeholders included. Every example must be something you would be happy to receive
verbatim — which mine was not.

---

## BUG-005 (continued) — how the confabulation was actually fixed, and what it revealed

**Status:** Fixed. The negative scenario now produces 0 findings, `unsupported_claim_rate` 0.000,
`evidence_coverage` 1.000.

**What did not work**

Two attempts, both by asking the model more firmly:

1. **Prompt wording** ("returning no findings is a correct answer") took it from 8 findings to 1-3,
   and no further.
2. **Tuning the relevance gate** traded one failure for the other. Kept loosely it admitted
   restatements; kept tightly it suppressed real contradictions on the *positive* scenario. One
   model judgement at 4B cannot hold both ends of that.

**What worked**

A structural rule: **a claim of conflict must cite both sides.** When the intent requires a
comparative operation, a finding fully supported by a single locator cannot be the answer - a
contradiction needs two things in tension, and a claim citing one side restates it.

Three details decided whether the rule was right or merely effective:

- **It reads the intent, not the claim.** `aurora_timeline_only` asks to *extract* a timeline, where
  a single-locator finding is exactly the answer. The same sentence answers one objective and is
  noise in another.
- **Locators, not documents.** A report that contradicts itself does so across two of its own lines,
  and requiring two *documents* would make a self-contradiction unreportable - which several of
  these objectives ask about.
- **Only fully-supported claims are dropped.** The first version also dropped claims whose citations
  failed to resolve, which broke the project's stance that unresolvable evidence is *kept and
  marked, never dropped* - and in practice it hid BUG-012 behind a clean-looking result.

**The rule fired nowhere for two evaluation runs** because three separate places construct the
replanning pipeline - the CLI, the orchestrator and the evaluation runner - and I had wired the
intent into one. That is the pipeline-duplication debt, biting exactly as predicted: a fix applied
to one copy silently did not apply to the others.

**What it revealed**

The contradiction scenario previously reported four findings; three were restatements, and every
metric counted them as successes. Removing them did not lower the agent's recall - it exposed it.
The real figure was always about one genuine contradiction per run, and the ceiling is the model.

So the build is still red, now on the opposite criterion: `aurora_contradiction` yields 0-1 findings
where 2 are planted. The threshold has not been moved. Of the two failures this is the better one -
an investigation that reports nothing is honest, and one that invents three findings is not - but it
is a real limit, not a fixed problem.

**Pattern**

A metric can be satisfied by the wrong thing. Four findings looked like better recall than one;
three of them were noise, and no metric in the suite could tell. The negative case was the only
test that could, which is the whole argument for having one.

---

## BUG-013 — Tasks inserted by replanning were invisible everywhere

**Found:** 2026-09-25, Phases 19/22 (found while collapsing the pipeline duplication)
**Severity:** High — the headline demo silently did not work
**Status:** Fixed

**Symptom**

A run whose event log contained `TASK_CREATED` for `task_008`, `task_009` and `task_010` reported
**7 tasks and 0 inserted** through the API. Mission Control's `INSERTED BY REPLAN` badge had
therefore never once fired, and neither had the animation built for it in Phase 22 — whose whole
purpose is that a viewer can point at the moment the plan changed.

I had seen this and misread it. The Phase 22 smoke test printed `inserted by replan: (none)` and I
recorded it as "this run inserted nothing". It had inserted three.

**Cause**

Two independent halves, which is why it survived a phase that was specifically about showing it.

1. **`run_mission` never carried the executed graph.** `result.plan` stayed as the planner wrote
   it. The replanning loop inserts tasks into the `TaskGraph`, not into the `Plan`, so anything
   reading `result.plan.tasks` saw the plan as written rather than as run. The evaluation runner
   had its own fix for this (`plan.model_copy(update={"tasks": graph.tasks})`); the orchestrator
   did not — and the API and UI read the orchestrator's result.
2. **`Task.created_by_revision` was never set.** The field existed, the API shaper read it, the UI
   keyed its badge off it, and `propose_task()` set `created_for_gap_id` and nothing else. So even
   once the tasks appeared, none was marked.

**Fix**

`run_mission` now carries the executed graph, and `_insert_tasks` stamps each task with the
revision that created it. A test asserts every inserted task carries both the revision and the gap
it was created for.

**Pattern**

The second half is the third occurrence of one shape: **a field defined, consumed, and never
written.** `RequiredOperation.optional` (BUG-010) and `_TOLERANCES` below the `__main__` guard
(BUG-011) were the others. None was visible from reading the code — each looked like working
plumbing, and each was only visible in output that was quietly wrong.

The first half is the pipeline duplication, which is now closed: one place constructs the
replanning pipeline, and the CLI and evaluation runner render its result.

---

## BUG-014 — Two of my own prompts disagreed about what a finding is

**Found:** 2026-09-25, Phase 13 (exposed by a newly added negative scenario)
**Severity:** Medium — a negative case failed on correct model behaviour
**Status:** Fixed

**Symptom**

`helix_budget_consistent` — a new negative case over a budget CSV, whose correct answer is no
findings — produced one:

```
The Helix budget file does not contradict itself on any line item amount
```

That is true, on-objective, and exactly what the relevance prompt asked for.

**Cause**

The prompts contradicted each other. `reasoning.md` said returning no findings is a correct answer;
`relevance.md` said *"keep a negative answer too: 'the two figures agree' answers 'do these
conflict?'"*. The model followed the second.

The tiebreak is evidence. **Absence cannot be cited.** A finding is bound to the locators it rests
on, and no locator says that something is not there — so a claim asserting absence can never be
evidence-bound, which makes it the one kind of claim this system has no way to support.

**Fix**

Both prompts now say it: a claim asserting an absence is not a finding, and when the answer is
"nothing" the output is an empty list rather than one claim announcing it. A negative conclusion
belongs in the report narrative, which is written from the fact that nothing was established.
Reasoning v4, relevance v3.

**Pattern**

Two prompts, each sensible alone, describing incompatible behaviour. Nothing in the type system or
the test suite could catch that — only a scenario could, and only a *second* negative scenario did.
One negative case was a single point of failure for the most important check in the suite.
