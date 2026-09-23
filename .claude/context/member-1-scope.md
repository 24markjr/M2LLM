# Member 1 — Scope

**Role:** Intelligence & Agent Engineer
**Owns:** the cognitive control loop that converts an objective into verified action.

This document exists to prevent two failure modes: building someone else's component, and
assuming someone else's component exists before it does.

---

## In scope

| Area | Deliverable | Phase |
|---|---|---|
| Domain schemas | The typed spine — every object crossing a boundary | 2 |
| Persistence | Runs, tasks, tool executions, findings, evidence, verifications, events | 3 |
| LLM abstraction | Provider protocol, Ollama + Echo providers, structured output with repair | 4 |
| Execution tracing | Event bus, the full run timeline, trace files | 5 |
| Intent engine | Natural-language objective to validated `Intent` | 6 |
| Planner | Candidate decomposition, DAG validation, deterministic repair | 7 |
| Task graph | Mutable dependency graph, state machine, versioned mutations | 8 |
| Tool system | Registry, tool contract, the built-in tool set | 9 |
| Tool router | Capability filtering, schema compatibility, LLM tiebreak | 10 |
| Execution engine | Dependency-aware concurrency, retry, fallback, cancellation, budget | 11 |
| Context manager | Working memory, compaction, retrieval with source locators | 12 |
| Reasoning engine | Findings, evidence binding, classification, computed confidence | 13 |
| **Evidence gap detector** | Claim decomposition, typed gaps, task proposals | 14 |
| Verification integration | `VerificationProvider` protocol + baseline verifier | 15 |
| **Adaptive replanning** | The closed loop, triggers, scoped re-reasoning, termination | 16 |
| Planning policy | Heuristic cost-aware action selection | 17 |
| Synthesis | The structured, evidence-backed final report | 18 |
| API | FastAPI endpoints + SSE streaming | 19 |
| **Evaluation harness** | Datasets, scorers, reports, regression detection | 20 |
| Frontend | Mission Control UI and live execution visualization | 21–22 |

The three bolded rows are the differentiators. If time runs short, they are the last things
to cut, not the first — see the plan's "minimum defensible MVP".

---

## Not in scope

These belong to other members. Member 1 consumes them through provider protocols and never
imports their implementations.

| Area | Owner | How Member 1 uses it |
|---|---|---|
| Context store internals | Member 2 (M2Context) | `ContextProvider.retrieve()` |
| Knowledge base internals | Member 3 | `KnowledgeProvider.search()` |
| Verification internals | Member 4 | `VerificationProvider.verify()` |

**Every one of these has a working local fallback**, so Member 1 is never blocked by another
member's timeline:

| Protocol | Local fallback | Selected by |
|---|---|---|
| `ContextProvider` | pgvector retrieval over ingested chunks (Phase 12) | `CONTEXT_PROVIDER` |
| `KnowledgeProvider` | Local document index | `KNOWLEDGE_PROVIDER` |
| `VerificationProvider` | `BaselineVerifier` — an independent second pass (Phase 15) | `VERIFICATION_PROVIDER` |

The fallbacks are not throwaway stubs. `BaselineVerifier` is a real independent check that
sees only the claim and its evidence, never the reasoning trail. If Member 4's service never
arrives, the verification story still holds; if it does arrive, it swaps in at one seam.

---

## The boundary rule

> Never import another member's implementation directly.

Selection is by environment variable. Every provider has a timeout and a documented
degradation path. A remote verifier that times out degrades to baseline and records
`VERIFICATION_DEGRADED` — verification is never silently skipped, because silently skipping
it would leave findings that look verified and are not.

This is enforced structurally: adapters live in `app/integrations/`, and nothing else in the
codebase knows a remote service exists.

---

## What "done" means for this contribution

A defensible statement of the work:

> I developed the intelligence and agent orchestration layer of JARVIS. The system converts
> natural-language objectives into validated task graphs, dynamically selects registered
> tools, executes tasks with dependency-aware scheduling, reasons over collected evidence,
> detects evidence gaps, invokes verification, and adaptively replans when the available
> evidence is insufficient. I also implemented the agent evaluation framework, execution
> tracing, model abstraction, and the integration interfaces for context, knowledge and
> verification services.

Every clause in that paragraph must be backed by a file and a measured number before it is
said out loud. The mapping from claim to evidence is the Phase 24 deliverable.
