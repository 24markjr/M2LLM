# Domain Schemas — the typed spine

**Phase:** 2 · **Location:** `backend/app/schemas/` · **Status:** complete

Every object crossing a component boundary is defined here. No engine exposes a raw `dict`
in a public signature (invariant #2).

---

## Why schemas came before engines

The schemas *are* the architecture. Writing them first forces the interfaces to be designed
rather than discovered halfway through an engine. Three specific payoffs, all already
realised:

1. **Invariants become types.** `Confidence` has no constructor that accepts a bare number,
   so "confidence is computed, never asked for" is enforced by the type system rather than
   by everyone remembering.
2. **The contract is checkable.** `test_schemas_package_imports_no_engine_code` asserts that
   importing `app.schemas` pulls in no engine, no provider, no database session. The spine
   cannot quietly become a consequence of the implementation.
3. **LLM output has a landing zone.** Every model uses `extra="forbid"`, so a model that
   invents a field fails validation loudly and triggers the repair loop (Phase 4) instead of
   silently producing a plausible object with information missing.

---

## Dependency order

```
common  ->  objective, intent, tool, evidence
        ->  verification  ->  finding
        ->  task  ->  plan
        ->  event, execution  ->  result
```

Strictly acyclic. `common` imports nothing from the package; `result` sits at the top.

---

## Modules

| Module | Types | Carries |
|---|---|---|
| `common.py` | `JarvisModel`, `FrozenModel`, `SourceLocator`, `FailureClass`, id helpers | Base config, identifier rules, retryability classification |
| `objective.py` | `Objective`, `ObjectiveScope`, `AttachedDocument`, `SuccessCriterion` | What the user asked, verbatim |
| `intent.py` | `Intent`, `Operation`, `RequiredOperation`, `Constraints` | What the system understood |
| `tool.py` | `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolSelection`, `SelectionMode` | Capability contracts and routing decisions |
| `evidence.py` | `Evidence`, `EvidenceRef`, `EvidenceGap`, `ClaimElement`, `GapType` | Support, and the absence of it |
| `verification.py` | `VerificationRequest`, `VerificationResult`, `VerificationIssue` | The independent check |
| `finding.py` | `Finding`, `Confidence`, `FindingClassification` | The unit of output |
| `task.py` | `Task`, `TaskStatus`, `TaskType`, `TaskResult`, `TaskDependency` | Graph nodes and the state machine |
| `plan.py` | `Plan`, `PlanValidationResult`, `PlanRevision`, `ViolationCode` | Decomposition and its audit trail |
| `event.py` | `ExecutionEvent`, `EventType`, `ExecutionTrace` | The run timeline — see `events.md` |
| `execution.py` | `ExecutionState`, `RunStatus`, `RunPhase`, `Observation`, `Budget` | Everything the agent knows |
| `result.py` | `FinalReport`, `ReportSection`, `AgentResult`, `Limitation` | What a human reads |

---

## The five load-bearing design decisions

### 1. `Confidence` cannot be constructed from a bare number

```python
Confidence(value=0.96)          # ValidationError — no such constructor
Confidence.compute(             # the only way
    refs=[...],
    strengths=[...],
    source_agreement=0.9,
    classification=FindingClassification.FACT,
)
```

The components travel with the value, so `confidence.explain()` renders
`0.72 (resolved 100%, strength 0.85, agreement 0.85, cap 1.00)`. A number that looks wrong
can be traced instead of argued about.

`compute()` is a pure function: identical evidence always yields an identical value. That is
what lets Phase 20 treat confidence as a measurable property rather than model noise.

### 2. Classification is derived, not declared

`Finding.classify()` recomputes classification from the evidence. The reasoning engine may
propose one; this is the ruling. Two validators back it up:

- A `FACT` with zero resolved evidence is rejected outright
- A confidence exceeding its classification's ceiling is rejected
  (`FACT` 1.0 · `INFERENCE` 0.85 · `HYPOTHESIS` 0.4 · `UNKNOWN` 0.2)

A model asserting 0.96 on a claim with unresolved citations has nowhere to put that number.

### 3. `CONTRADICTED` is not the same as `UNSUPPORTED`

An unsupported claim is unproven — a gap to fill, and the replanning loop should try.
A contradicted claim is *wrong*, and more evidence will not rescue it. `Finding.is_rejected`
and `VerificationResult.actionable` encode that distinction, which is what stops the agent
burning replan iterations trying to rescue a claim the sources refute.

### 4. Failures are classified at the point of failure

`FailureClass` splits transient (`TIMEOUT`, `CONNECTION_ERROR`) from permanent
(`SCHEMA_VIOLATION`, `UNSAFE_EXPRESSION`). `TaskResult` refuses to be constructed as failed
without one, because the retry policy cannot decide "retry or fall back" without it.

### 5. Derived values are properties, not `@computed_field`

Discovered by the round-trip test in this phase. A `@computed_field` is serialized into the
model's JSON, and with `extra="forbid"` the model then **rejects its own output** on
re-validation — which would break persistence, trace replay and the evaluation harness's
reconstruction of stored runs. Derived values belong in API response models (Phase 19), not
in the wire contract of a stored object.

---

## Validators that encode architecture

These reject states the system must never reach:

| Model | Refuses | Because |
|---|---|---|
| `Finding` | `FACT` with no resolved evidence | The invariant the architecture exists to protect |
| `Finding` | Confidence above its classification ceiling | A hypothesis cannot present as near-certain |
| `VerificationResult` | A rejection with no issue | The replanning loop cannot act on a bare verdict |
| `VerificationResult` | `degraded=True` with no reason | Degradation is never silent |
| `EvidenceGap` | `resolved=True` with no task id | The loop must be auditable |
| `TaskResult` | Failure with no `failure_class` | Retry policy needs it |
| `Task` | Self-dependency, duplicate dependencies | Would corrupt the graph |
| `Plan` | Duplicate ids, dangling dependencies | Unexecutable |
| `PlanValidationResult` | `valid=False` with no violation | An unexplained rejection is not diagnosable |
| `PlanRevision` | A revision that changes nothing | Should not have been recorded |
| `Intent` | Duplicate operations; clarification with no question | Useless output |
| `FinalReport` | Verified findings without resolved evidence | Last line of defence before a human reads it |
| `AgentResult` | Success with no report; failure with no error code | Inconsistent outcomes |

`VerificationRequest` is notable for a field it **lacks**: there is no `reasoning`,
`observations` or `plan`. A verifier shown the argument tends to be persuaded by it. The
absence is the contract, and a test asserts those field names never appear.

---

## Closed vocabularies

Four enums are closed on purpose, and each is checked by a test:

| Vocabulary | Size | Guard |
|---|---|---|
| `Operation` | 18 | Every operation must be satisfiable by some `TaskType` |
| `TaskType` | 16 | Every type must map to a capability and to operations |
| `TaskStatus` | 8 | Matches the specification exactly |
| `EventType` | 38 | Every event in the spec's sample trace must be emittable |

`TASK_CAPABILITY` and `TASK_SATISFIES` are the bridges: capability drives deterministic
routing (Phase 10), operation coverage drives plan validation (Phase 7).

---

## Test coverage

`backend/tests/unit/test_schemas.py` — 81 tests. Beyond ordinary validation coverage, these
encode the invariants as executable assertions:

- `test_confidence_cannot_be_conjured_from_a_bare_number`
- `test_a_fact_requires_resolved_evidence`
- `test_classification_is_recomputed_from_evidence_not_trusted`
- `test_contradicted_finding_is_rejected_not_merely_unverified`
- `test_verification_request_carries_no_reasoning_trail`
- `test_model_deliberation_is_stripped_before_persistence`
- `test_a_task_cannot_complete_without_running`
- `test_report_refuses_to_present_unsupported_claims_as_verified`
- `test_schemas_package_imports_no_engine_code`
- `test_json_round_trip_is_lossless`

A future change that quietly breaks one of these fails here rather than in a demo.
