# Unit tests

**Location:** `backend/tests/unit/` · **Model:** `EchoProvider` · **Strategy:**
[testing-strategy.md](testing-strategy.md)

```bash
cd backend
pytest tests/unit -q
pytest tests/unit -q --cov=app --cov-report=term
pytest tests/unit/test_reasoning.py -q -k locator
```

## The files

| File | Covers |
|---|---|
| `test_schemas.py` | the 97 types: validators, round-trips, computed properties |
| `test_config.py`, `test_agent_config.py` | the two configuration surfaces and `clamp()` |
| `test_llm.py` | provider protocol, structured output, the repair loop, prompt rendering |
| `test_llm_isolation.py` | **invariant 1** and the no-`eval` rule, by reading the source tree |
| `test_invariants.py` | **the rest of the "must not do" list** — see the strategy doc |
| `test_adversarial.py` | **hostile, broken and empty input** |
| `test_intent.py` | operation mapping, synonyms, clarification |
| `test_planner.py` | validation, the repairs, execution waves |
| `test_tools_and_router.py` | registry, capability filtering, deterministic-first routing |
| `test_execution.py` | wave scheduling, retry, fallback chains |
| `test_context.py` | compaction, and that it never loses a locator |
| `test_reasoning.py` | evidence binding, classification, computed confidence |
| `test_relevance_gate.py` | claims that are supported but do not answer the objective |
| `test_evidence_gap.py` | gap detection, and that the decision is deterministic |
| `test_verification.py` | the verdict vocabulary, and declared degradation |
| `test_replanning.py` | the closed loop: bounded, and every stop records a distinct reason |
| `test_planning_policy.py` | action scoring and selection |
| `test_synthesis.py` | report assembly; every figure counted, not described |
| `test_evaluation.py` | the metrics, the negative case, the positive-case blind spot |
| `test_events.py` | the append-only log, `t_offset_ms`, redaction |
| `test_api.py` | the error contract and **SSE reconnection** |
| `test_orchestration.py` | the headless pipeline's failure modes |
| `test_recording.py` | recordings, and that a snapshot matches what the live routes serve |

## How these are written

**A test name states the claim.** `test_a_contradicted_finding_is_not_retried`, not
`test_replan_3`. The name is what a reader sees in a failure, so it should say what broke rather
than which case number did.

**A docstring says why the behaviour matters**, and where it came from. Several record a real
defect — `test_a_citation_with_the_quoted_line_appended_still_parses` exists because a live run
came back entirely `UNKNOWN` at zero confidence. A test whose reason is written down survives a
refactor that a test asserting a mechanism does not.

**Assertions carry a message when the failure would otherwise be cryptic.**
`assert added <= MAX_ACTIONS_PER_ITERATION, "one iteration flooded the graph"`.

**Fixtures are explicit, not clever.** `_findings(...)` and `_verdicts(...)` build the JSON a
model would return. A shared factory that guessed at intent would make the tests harder to read
than the code.

## Coverage

82% overall; `app/intelligence/**` and `app/schemas/**` at 90–100%, meeting the ≥ 80% target. The
CI floor is 75% — see the strategy doc for why it is deliberately below the current figure.

Two modules are low and deliberately so:

- `app/llm/ollama.py` at 40% — the HTTP paths are exercised by `tests/integration/test_ollama_live.py`,
  which needs a real model and is excluded from CI. Mocking them here would test the mock.
- `app/tools/loader.py` at 69% — the PDF and CSV edge paths need real fixture files; the
  adversarial suite covers unreadable and corrupt input.
