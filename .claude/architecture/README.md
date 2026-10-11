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
| `verification.md` | The verifier contract and its four implementations | 15, 26 |
| `security.md` | Untrusted document content: scanning, wrapping, what stops an injection | 27 |
| `knowledge-layer.md` | Entities, relationships, claims; grounding, resolution, conflicts, timeline, search | 28 |
| `memory.md` | Working, episodic and semantic memory across missions; why it never feeds a run | 33 |
| `media.md` | Images, scans, video and audio: read (OCR), seen (vision model, weaker evidence), heard (speech) | 39 |
| `retrieval.md` | Stored, workspace-scoped retrieval: pgvector or memory, two chunkers, hits cited at their closest line | 40 |
| `evidence-locker.md` | Every input an evidence item: content-addressed originals, append-only custody, integrity before every mission | 43 |
| `cases.md` | Cases holding investigations and evidence; counters computed; the Professional view and plain step labels | 44 |
| `challenge.md` | Challenge a finding: counter-evidence, its own lines, the verifier on the counter lines, authority; before and after; the challenge benchmark | 48 |
| `hypotheses.md` | Competing explanations proposed by the model, ranked by support computed from verified findings; undetermined questions left open with the next best evidence | 47 |
| `confidence.md` | Confidence from named factors that add up; why it is not higher; the evidence chain from claim to conclusion | 46 |
| `statements-and-authority.md` | Statement types ruled from evidence (no single-source FACT); source authority tiers, reported on both sides of a contradiction and never deciding one | 45 |

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
