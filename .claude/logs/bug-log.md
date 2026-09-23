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
