# Agent Architecture — the LLM layer

**Phases:** 4 (LLM abstraction), 5 (event bus) · **Status:** complete

---

## The one-way door

```
   any intelligence component
              |
              v
   app/llm/provider.py : LLMProvider     <-- the ONLY door to a language model
              |
     OllamaProvider  |  EchoProvider
```

Invariant #1. `tests/unit/test_llm_isolation.py` fails if any module outside `app/llm/`
imports an HTTP client, and separately if anything outside `config.py` reads `os.environ`.
That test is what turns "the LLM is a component, not the architecture" from a claim into a
checkable property.

The protocol is deliberately small — `complete`, `embed`, `model_id`, `health`. Anything
larger would leak provider-specific capability into the seam and make swapping one out a
refactor instead of a config change.

| Provider | `LLM_PROVIDER` | Role |
|---|---|---|
| `OllamaProvider` | `ollama` | Local inference. The only module that speaks HTTP to a model |
| `EchoProvider` | `echo` | Deterministic fixtures. CI runs the full suite with no network, no GPU, no secrets |

`EchoProvider` is not a stub. It proves the abstraction is real — an interface with one
implementation is a guess about what the seam should be.

---

## Structured output: the repair loop

The highest-risk component in the project. Every engine depends on getting a valid typed
object out of a 4B local model.

```
generate_structured(provider, schema, prompt, role=...)
    |
    |-- inject JSON Schema, enable provider JSON mode
    |-- call
    |-- extract JSON  (fences, prose, arrays)
    |-- validate against the Pydantic model
    |      |
    |      +-- ValidationError -> re-prompt WITH THE ERRORS APPENDED  --+
    |                                                                   |
    |      <------------------------------------------------------------+
    |            (up to structured_output.max_repairs)
    |
    +-- exhausted -> StructuredOutputError carrying the raw text
```

Three decisions make it work:

**The errors go back to the model.** Not "try again" — *"evidence.0.locator.page: Input
should be a valid integer"*. A model told what was wrong fixes it far more often than one
told it failed.

**`extra="forbid"` from Phase 2 is what makes the loop trigger.** A model inventing a field
fails validation loudly instead of producing a plausible object with information silently
dropped.

**It never guesses.** After exhausting repairs it raises, carrying the raw text and the
validation errors. The caller decides whether to degrade the task or fail it. A layer that
substituted a default would make every downstream finding untrustworthy in a way nothing
could detect.

### `extract_json` tolerates what models actually emit

Code fences, `Here is the result:` preambles, trailing `Hope that helps!`. Tolerating that
is not sloppiness — it is the observed behaviour of the models this system is built for, and
refusing to parse it would spend repair attempts on formatting quirks rather than real
schema failures.

The parser walks balanced delimiters while tracking string state, starting from whichever of
`{` or `[` appears first. (Checking `{` first would silently return the leading object from
a JSON array — a bug caught by the Phase 4 tests.)

---

## Finding: qwen3 is a reasoning model

Discovered while running Phase 4's acceptance tests against the real model, and worth
recording because it changes how the provider is built.

Ollama returns a reasoning model's deliberation in a **separate `thinking` field**, and with
a modest token budget the deliberation consumes all of it:

```
response  = ''
thinking  = 'Hmm, the user just asked me to reply with the single word "ready"...'
done_reason = 'length'
```

Two consequences:

**Practical.** `think: false` is sent on every request, configurable per role in
`models.yaml`. Without it, a `num_predict` of 64 produces no answer at all, and every
evaluation run pays for deliberation tokens it then discards.

**Architectural.** `thinking` is, definitionally, model deliberation — exactly what
invariant #3 keeps out of the record. The provider reads only `response` and never touches
the field. This is the *first* line of defence; event-bus redaction is the second. A test
asserts the response object has no `thinking` attribute and no `<think>` markers.

### Measured on the configured model

| Metric | Value |
|---|---|
| Model | `qwen3:4b` (2.5 GB, fits fully in 6 GB VRAM) |
| Repair rate | 0.00 over 3 structured calls |
| Mean latency | ~1.6 s per structured call |

A small sample, stated as such. It is a measurement, not a result — Experiment 001 (Phase
20) is where it becomes a comparison across models on identical scenarios. Asserting a
threshold here would be inventing a finding.

---

## Two configuration surfaces

| Surface | Holds | Owner |
|---|---|---|
| `.env` -> `Settings` | Where things are, and **hard safety ceilings** | Operator, per machine |
| `.agent/config/*.yaml` | **How the agent behaves** | Engineer, committed and reviewed |

**The rule that keeps them safe: YAML can never exceed an `.env` ceiling.** `clamp()`
enforces it and logs every clamp:

```
agent_config_clamped  setting=replanning.max_iterations requested=8 applied=3
```

Behaviour policy is tunable from inside the repository; safety bounds are not. A silently
ignored setting is impossible, because a clamp always says so.

`.env` also wins on model identity and determinism — `OLLAMA_MODEL` overrides the YAML,
because Experiment 001 swaps models with an environment variable.

### Prompts are versioned assets

`.agent/prompts/*.md`, never Python string literals. A prompt buried in code is invisible in
review, untracked in evaluation, and impossible to attribute a metric shift to. Loaded by
role, with front matter carrying `version`, `output_schema` and `phase`.

`render()` is strict: an unfilled `{{placeholder}}` raises rather than reaching the model as
literal text, which is the kind of defect that produces confidently wrong output instead of
an error.

---

## The event bus (Phase 5)

```
engine -> RunEventEmitter -> EventBus --[redact]--> sinks
                                                     |-- MemoryEventSink
                                                     |-- StreamEventSink  (SSE, Phase 19)
                                                     |-- TraceFileSink    (TRACE_TO_FILE=1)
                                                     +-- DatabaseEventSink (Phase 3)
```

Invariant #4 — a run must be reconstructable from its event log alone — only holds if there
is exactly one way to record a transition. Engines take a `RunEventEmitter` bound to one run
rather than a bus plus a run id plus a clock: threading three things through ten components
is how a transition eventually goes unrecorded.

**Redaction happens once, in `emit()`**, before any sink sees the event. A component may put
raw completion text in a payload while debugging; it will not reach the database, the
stream, or a trace file.

**Sink failures are isolated.** A failing sink logs and is skipped. Losing a trace file is
an inconvenience; losing the investigation is not.

**`RunClock` uses `perf_counter`, not wall-clock.** A system clock adjustment mid-run would
otherwise produce negative offsets and a trace that cannot be ordered.

**A lagging SSE subscriber drops events rather than stalling the run.** Backpressure onto
the agent would be the wrong trade — a client recovers its gap by replaying from
`Last-Event-ID`; a stalled investigation does not recover at all.

---

## Deferred

| Item | Phase | Why |
|---|---|---|
| `DatabaseEventSink` | 3 | The persistence layer does not exist yet |
| Prompt assets themselves | 6-18 | Each prompt ships with the engine that uses it |
| `tools.yaml` / `evaluation.yaml` typing | 9-10 / 20 | Typed when code reads them, not before |
| Full `agent.yaml` typing | 16 | Only the ceiling fields are consumed so far |
