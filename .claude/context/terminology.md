# Terminology

These words are used precisely and consistently across code, documentation, events, the API
and the UI. Where a term maps to a type, the type is authoritative.

Imprecise vocabulary is not a cosmetic problem here: if "finding" sometimes means a model's
raw output and sometimes means a verified conclusion, then "evidence coverage" measures
nothing in particular.

---

## Core terms

### Objective
What the user asked for, in their own words. Raw natural language, unprocessed.
*"Find inconsistencies between the project timeline and budget."*
→ `app.schemas.objective.Objective`

### Intent
The system's structured interpretation of an objective: the goal, the operations required to
achieve it, the constraints, and the expected output format. Produced by the intent engine;
validated against a known operation vocabulary.
→ `app.schemas.intent.Intent`

### Plan
A proposed decomposition of the intent into tasks and dependencies. A plan is *candidate*
until it passes validation. An invalid plan is never executed — it is repaired, re-prompted,
or the run fails cleanly with `PLAN_INVALID`.
→ `app.schemas.plan.Plan`

### Task
One unit of work with a type, inputs, a status and dependencies. Tasks are the nodes of the
task graph.
→ `app.schemas.task.Task`

States: `PENDING` → `READY` → `RUNNING` → `COMPLETED`, with `FAILED`, `RETRYING`, `BLOCKED`
(a descendant of a terminal failure) and `SKIPPED` (made unnecessary or impossible).

### Task graph
The live, mutable DAG of tasks and dependencies. Not a fixed plan artifact — replanning
inserts, replaces and invalidates nodes mid-run, and every mutation is versioned.
→ `app.intelligence.graph.TaskGraph`

### Tool
A registered capability with a name, description, input schema, output schema, capability
set and cost hint. Tools are the only way the agent affects or reads the world.
→ `app.tools.base.Tool`

### Tool routing
Choosing which tool accomplishes a task. Deterministic capability filtering and schema
compatibility come first; the model only breaks ties between remaining candidates. Every
selection records its reason and its mode.

### Observation
The recorded result of executing one task: what the tool returned, or how it failed.
Observations accumulate into the run's working context.
→ `app.schemas.execution.Observation`

### Finding
A structured claim the agent has derived, carrying its classification, evidence references,
computed confidence and verification status. Findings are the unit of output — the report is
assembled from them.
→ `app.schemas.finding.Finding`

**Classification:**

| Value | Meaning |
|---|---|
| `FACT` | Every element of the claim traces to resolved evidence |
| `INFERENCE` | Combines two or more resolved sources with a stated reasoning step |
| `HYPOTHESIS` | Partially supported — at least one element is unresolved |
| `UNKNOWN` | No resolved evidence |

### Evidence
A pointer to specific content that supports a claim, with an exact source locator: document,
page or row, and character span. Evidence is *resolved* when the citation was matched against
actually-retrieved content, and `UNRESOLVED` when it was not.

An unresolved citation is recorded, never silently dropped. It feeds gap detection and the
unsupported-claim metric.
→ `app.schemas.evidence.Evidence`

### Confidence
A number in [0, 1] **computed** by the system from evidence strength, source agreement,
citation resolution rate and classification.

It is never taken from the model's self-report. A model asserting 0.96 on a claim with
unresolved citations does not get 0.96.
→ `app.schemas.finding.Confidence`

### Verification
An independent check of a claim against its evidence, performed without access to the
reasoning trail that produced the claim. Independence is the point: a verifier that can see
the reasoning tends to agree with it.

Statuses: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`.
→ `app.schemas.verification.VerificationResult`

### Evidence gap
A specific, named element of a claim that available evidence does not support — *"the
approved baseline completion date"*, not *"more evidence"*. Typed, deterministic, and mapped
to a proposed task that would close it.
→ `app.schemas.evidence.EvidenceGap`

Types: `MISSING_SOURCE`, `MISSING_BASELINE`, `UNRESOLVED_CITATION`, `CONFLICTING_SOURCES`,
`INSUFFICIENT_GRANULARITY`, `STALE_SOURCE`.

### Replan
A mid-run revision of the task graph, triggered by an unsupported finding with an actionable
gap, a permanent task failure with a viable alternative, an invalidated assumption, or a
source conflict needing a tiebreak. Bounded by `MAX_REPLAN_ITERATIONS`, and every
termination records its reason.

---

## Supporting terms

### Run / Mission
One complete execution, objective to report. **Run** is the internal term (`agent_runs`,
`run_id`); **mission** is the user-facing term (the API and UI use it). Same thing.

### Execution event
One record in the append-only run timeline, carrying a type, a payload and `t_offset_ms`
relative to `RUN_STARTED`. The run is fully reconstructable from its events alone.
→ `app.schemas.event.ExecutionEvent`

### Operational transparency
Exposing what the agent *did* — task selected, tool selected, evidence retrieved, finding
generated, verification result, replan decision — as distinct from exposing raw model
deliberation, which is never surfaced or persisted.

### Provider
A swappable implementation behind a protocol: `LLMProvider`, `ContextProvider`,
`KnowledgeProvider`, `VerificationProvider`. Selected by environment variable, each with a
timeout and a documented degradation path.

### Scenario
An end-to-end specification of one agent behaviour, with expected trace events and outcomes.
Lives in `.agent/scenarios/`.

### Trace
The recorded event log of a real run. Used as a regression baseline and as demo insurance.
Never hand-authored.

---

## Words to avoid

| Avoid | Use instead | Why |
|---|---|---|
| "answer" | result, report, finding | JARVIS investigates; it does not answer |
| "chat" | mission, investigation, run | The interaction model is not conversational |
| "step" | task | `Task` is a type with states and dependencies |
| "confidence score" (from the model) | computed confidence | The distinction is the whole architecture |
| "agent thinks" | the agent selected / executed / verified | Deliberation is not exposed |
| "AI decides" | name the component: the router selected, the planner produced | "AI" hides which component is responsible |
