# Architecture documentation

Subsystem detail. Start with [`../context/architecture.md`](../context/architecture.md) for
the system-level view, then come here for the component you are working on.

Each document is written when its phase lands — an architecture document written before the
code is a guess, and one written after the code is a record.

| Document | Covers | Phase |
|---|---|---|
| `system-architecture.md` | Deployment shape, persistence, request lifecycle | 3 |
| `agent-architecture.md` | The runtime, the LLM layer, the planning policy | 4, 17 |
| `task-graph.md` | DAG semantics, state machine, mutation and versioning | 7, 8 |
| `tool-system.md` | Tool contract, registry, routing, fallback chains | 9, 10 |
| `reasoning-engine.md` | Evidence binding, classification, computed confidence, gaps | 13, 14 |
| `verification-loop.md` | Independent verification and the closed replanning loop | 15, 16 |
| `integrations.md` | Provider protocols; the frontend contract | 12, 15, 22 |

## What belongs in an architecture document

- The mechanism: what the component actually does, in enough detail to reimplement it
- The contracts it exposes and depends on
- The failure modes it handles, and the ones it deliberately does not
- Why it is shaped this way, where that is not obvious (link the ADR rather than re-arguing)

## What does not belong here

- Build order or scheduling — that is `../implementation/implementation-plan.md`
- Decision rationale for contested choices — that is an ADR in `../decisions/`
- API surface detail — that is `../api/`
- Anything that duplicates a docstring. If it belongs next to the code, put it next to the
  code.
