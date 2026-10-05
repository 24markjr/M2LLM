# `.claude/` — engineering memory

This directory answers:

> **Why is JARVIS built this way?**

It holds the reasoning behind the system: architecture, decisions, implementation history,
and the record of what was tried and what broke. It is not user documentation and it is not
source code.

The counterpart is `.agent/`, which answers *"does the agent actually work?"*.

## Why this exists

A project of this kind accumulates decisions faster than it accumulates code — why a DAG
instead of a chain, why confidence is computed rather than asked for, why verification runs
without the reasoning trail. Six weeks later, the code shows *what* was decided and nothing
about *why*. Reconstructing the why from the code is how good decisions get accidentally
reversed.

So: every significant architectural or implementation change updates this directory in the
same change that touches the code. A phase is not done until it does.

## Layout

| Directory | Contents |
|---|---|
| `context/` | Orientation: the problem, the scope, the architecture, the vocabulary |
| `architecture/` | How each subsystem works, in detail |
| `implementation/` | The phased plan and per-phase implementation notes |
| `decisions/` | ADRs — one file per architectural decision |
| `integrations/` | Contracts with Members 2, 3 and 4 |
| `api/` | Endpoint, schema and event documentation |
| `testing/` | Testing strategy and the evaluation approach |
| `changes/` | Changelog |
| `logs/` | Development log, bug log, experiment log |

## Start here

New to the project, in order:

1. [`context/project-overview.md`](context/project-overview.md) — the problem and the answer
2. [`context/terminology.md`](context/terminology.md) — the vocabulary, used precisely everywhere
3. [`context/architecture.md`](context/architecture.md) — how the pieces fit
4. [`implementation/implementation-plan.md`](implementation/implementation-plan.md) — the build order
5. [`decisions/`](decisions/) — why, for the contested choices

Then, for the integration of Members 3 and 4 (Phases 25-35):

6. [`decisions/ADR-009-port-teammates-in-process.md`](decisions/ADR-009-port-teammates-in-process.md) — why port rather than call
7. [`integrations/teammate-port.md`](integrations/teammate-port.md) — every teammate feature, the
   original file, where it lives now and what changed
8. [`implementation/integration-plan-phases-25-35.md`](implementation/integration-plan-phases-25-35.md) — the plan, its decisions (D1-D6) and what each phase built
9. [`architecture/knowledge-layer.md`](architecture/knowledge-layer.md),
   [`architecture/security.md`](architecture/security.md),
   [`architecture/verification.md`](architecture/verification.md),
   [`architecture/memory.md`](architecture/memory.md) — the ported subsystems
10. [`logs/experiment-log.md`](logs/experiment-log.md) and [`logs/bug-log.md`](logs/bug-log.md) —
    what was measured, and what broke

## The documentation rule

Any change that alters architecture or behaviour updates, in the same change:

- the relevant `architecture/` or `implementation/` document
- `changes/changelog.md`
- `logs/development-log.md`
- a new ADR, if the change is architectural

Undocumented architectural changes are not acceptable. A decision that exists only in the
code is a decision nobody can evaluate, defend, or safely revisit.

## ADR index

| ADR | Decision | Status |
|---|---|---|
| [001](decisions/ADR-001-modular-monolith.md) | Modular monolith, not microservices | Accepted |
| [002](decisions/ADR-002-postgresql.md) | PostgreSQL as the primary store | Accepted |
| [003](decisions/ADR-003-ollama.md) | Ollama behind a provider abstraction | Accepted |
| [004](decisions/ADR-004-custom-orchestration.md) | Custom orchestration, not an agent framework | Accepted |
| [005](decisions/ADR-005-pgvector.md) | pgvector, not a separate vector database | Accepted |
| [006](decisions/ADR-006-task-graph.md) | A mutable DAG, not a linear chain | Proposed |
| 007 | *Never written* - see [`decisions/README.md`](decisions/README.md) | - |
| [008](decisions/ADR-008-sse-over-websocket.md) | Server-sent events, not WebSocket | Accepted |
| [009](decisions/ADR-009-port-teammates-in-process.md) | Port Members 3 and 4 into the backend, not call them as services | Accepted |
| [010](decisions/ADR-010-neo4j-knowledge-graph.md) | Neo4j for the knowledge graph, optional, behind one protocol | Accepted |
| [011](decisions/ADR-011-3d-knowledge-explorer.md) | The 3D knowledge explorer: vanilla 3d-force-graph, pure logic beside it | Accepted |
