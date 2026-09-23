# ADR-001 — Modular monolith, not microservices

## Status

Accepted — 2026-09-23 (Phase 1)

## Context

JARVIS has ten distinct intelligence components — intent, planner, graph, router, execution,
context, reasoning, evidence gap, replanning, synthesis — plus a tool runtime, an API and an
evaluation harness. Listed out, that looks like a service diagram, and the temptation to
deploy it as one is real.

The actual runtime characteristics argue otherwise:

- **The components are extremely chatty with each other.** A single replan iteration touches
  reasoning, verification, gap detection, the planning policy, the task graph and the
  execution engine — several times. Over HTTP that is dozens of round trips per iteration,
  each with serialization cost and failure modes, in a loop that is already the hardest part
  of the system to reason about.
- **They share one mutable object: the task graph.** Replanning mutates a graph that the
  execution engine is concurrently scheduling from. Distributing that means distributed
  locking or an event-sourced rebuild — a hard problem, adopted voluntarily, for no benefit.
- **There is one user and one run at a time.** No component needs independent scaling. The
  bottleneck is local model inference, which is a single process on a single GPU.
- **Debugging the cognitive loop is the main development activity.** A single process with a
  single stack trace and a single debugger is worth a great deal here.

## Decision

A modular monolith: one deployable FastAPI backend, with each intelligence component as its
own package under `app/intelligence/`, communicating through typed Pydantic contracts.

Boundaries are enforced by discipline and tests, not by network hops:

- Every cross-component value is a Pydantic model from `app/schemas/` (invariant #2)
- The model is reachable only through `app/llm/` (invariant #1, enforced by test)
- External members are reached only through provider protocols in `app/integrations/`
- Engines talk to repositories, never to database sessions directly

## Reason

- **A network boundary is not an abstraction boundary.** Splitting into services would not
  make the components more decoupled; it would make the existing coupling expensive and
  harder to see. Typed contracts give the decoupling; HTTP would only add latency and
  partial-failure modes.
- **The replanning loop is the project's differentiator and its hardest code.** Every
  decision should make that loop easier to build correctly. Distribution makes it harder.
- **Microservices here would be resume-driven architecture** — complexity that looks
  impressive and buys nothing at this scale. It would cost time that belongs to evidence-gap
  detection and the evaluation harness, which are what the project is actually about.

## Consequences

**Accepted costs**

- Components cannot be scaled or deployed independently. Not needed: one run at a time,
  bottlenecked on local inference.
- A crash takes down the whole backend. Acceptable for an MVP; runs are persisted, so state
  survives.
- Module boundaries need active maintenance, since nothing physically prevents a shortcut
  import. Mitigated by the isolation tests and by code review against the invariants.

**Gained**

- One process, one stack trace, one debugger for the loop that matters most
- No serialization overhead inside the cognitive cycle
- The task graph can be a shared in-memory object with a normal state machine
- Docker Compose runs Postgres and one backend, not eight containers

## Future service seams

The boundaries are drawn so the monolith could be cut later without redesign:

| Extractable | Already separable because |
|---|---|
| Execution engine + tool runtime | Communicates only via `Task` / `ToolCall` / `Observation` |
| Verification | Already a provider protocol with a remote implementation |
| Context + retrieval | Already a provider protocol |
| Evaluation harness | Reads persisted runs; no runtime coupling |

Nothing in the MVP depends on that ever happening. The seams exist so the decision is
reversible, not because reversing it is planned.

## Revisit if

Multiple concurrent runs become a requirement and local inference stops being the
bottleneck — for instance if the system moves to a hosted model and needs to serve several
investigations at once. The execution engine would be the first thing to extract.
