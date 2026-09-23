# ADR-006 — A mutable task DAG, not a linear chain

## Status

**Proposed** — 2026-09-23 (Phase 1). Moves to Accepted when Phases 7–8 land and the
mutation semantics are proven against the replanning scenarios.

## Context

The agent needs some representation of "the work to be done". Three shapes were considered:

**1. A linear chain.** Steps in sequence, each feeding the next. This is what most agent
demos use.

**2. A static DAG.** Tasks with dependencies, computed once from the plan, then executed.

**3. A mutable DAG.** Tasks with dependencies, computed from the plan, and then *edited by
the agent during execution*.

The investigation domain settles it. Given four documents and an objective about timeline
and budget consistency:

- Extracting the timeline from document A and the budget from document B are **independent**.
  A chain serializes them for no reason, and on local inference that is the difference
  between a demo that feels alive and one that does not.
- Comparing dates **depends on both** extractions. The dependency is real and must be
  enforced, not left to ordering luck.
- When verification rejects a finding and gap detection names a missing baseline, a **new
  task appears that nobody planned** — mid-run, in response to what was learned.

That last point is the project's differentiator. A static DAG cannot express it. A linear
chain cannot express either parallelism or insertion.

## Decision

A mutable directed acyclic graph.

- Nodes are `Task` objects with an explicit state machine:
  `PENDING → READY → RUNNING → COMPLETED`, plus `FAILED`, `RETRYING`,
  `BLOCKED` (transitive descendant of a terminal failure) and `SKIPPED`.
- Edges are dependencies. A task becomes `READY` only when every dependency is `COMPLETED`.
- The graph exposes a mutation API — `insert_task_before/after`, `replace_subgraph`,
  `invalidate_downstream` — used by the replanning controller (Phase 16).
- **Every mutation is versioned.** The graph carries a `revision` counter and an append-only
  mutation log, and acyclicity is re-validated after every mutation.
- Every mutation is attributable: an inserted task records which evidence gap or failure
  caused it.

## Reason

- **Parallelism is free and real.** Independent extractions run concurrently because the
  graph says they are independent, not because someone remembered to parallelize them.
- **Dependencies are enforced, not hoped for.** `ready_tasks()` is the single place
  ordering is decided, which makes "no task ran before its dependencies" an assertable
  property rather than an emergent one.
- **Mutation is the mechanism behind the headline feature.** "The agent realised its
  evidence was insufficient and added a task to get more" is a graph insertion. Without
  mutability there is no closed loop, and without the closed loop there is no contribution.
- **Versioned mutations make replanning inspectable.** The UI can show *the moment the plan
  changed* and what caused it. A viewer can point at it. That is worth a great deal in a
  demonstration, and more in debugging.
- **Cycle detection is a real correctness property.** Small models do emit plans with
  dependency cycles. Detecting them, reporting the offending path, and repairing or failing
  cleanly is engineering, not ceremony.

## Consequences

**Accepted costs**

- More complex than a chain: a state machine, readiness computation, cycle detection,
  descendant blocking, mutation versioning.
- Mutating a graph while the scheduler reads it needs care. Mitigated by the monolith
  (ADR-001) — one process, one event loop, mutations applied between scheduling batches
  rather than during them.
- Serialization must round-trip exactly, since the graph is persisted and streamed to the UI.

**Gained**

- Concurrency with correct ordering
- A representation the replanning loop can actually edit
- A visual artifact for the UI that means something
- Testable properties: readiness is never granted to a task with an incomplete ancestor;
  the graph is acyclic after every mutation

## Open questions for Phase 8

1. Should `SKIPPED` propagate to descendants, or should they be `BLOCKED`? Leaning toward
   `BLOCKED` with a distinct reason, so the report can distinguish "we chose not to" from
   "we could not".
2. Should a replan be able to remove a `COMPLETED` task's results from context, or only add?
   Add-only is simpler and safer; removal may be needed when an assumption is invalidated.
3. How many mutation revisions to retain for display — all of them, or a window?

These are resolved when Phases 8 and 16 land, and this ADR is updated with the answers
before it moves to Accepted.
