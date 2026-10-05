# Memory across investigations (Phase 33)

Member 4's three memory tiers, ported into JARVIS. Code: `backend/app/memory/`, schemas
`app/schemas/memory.py`, API `app/api/v1/memory.py`, UI `#/memory` and the graph explorer's pop-up.

## The three tiers

| Tier | Member 4 | JARVIS | Where |
|---|---|---|---|
| **Working** (T10) | A mutable `WorkingMemory` object, filled during a run; `snapshot()` reduced evidence to a count | `WorkingMemorySnapshot`, **derived** from the finished `MissionResult` (`distill.working_snapshot`): objective, plan steps (including tasks the replanning loop inserted), evidence count (observations), hypotheses, findings, start time | Archived with the run |
| **Episodic** (T11) | SQLite: `episodic_memory` (question, answer, sources, verification status) and `investigations` (archived snapshots); `search(keyword, limit=5)` as `LIKE`, newest first | Postgres `memory_episodes` (one per finding: objective, claim, resolved sources, verification status) and `memory_investigations` (the snapshot). `search` is `ILIKE` on objective or claim, newest first, 5 by default, `%` and `_` searched literally | Postgres |
| **Semantic** (T12) | SQLite subject-predicate-object facts with `confidence=1.0`; `query(subject?, predicate?)` by exact match | `Fact`s between `KnownEntity`s, merged across runs by normalised name, each with its `support`: the (run, source line) pairs that asserted it. Queried by normalised subject and predicate | Neo4j (`GRAPH_STORE=neo4j`), else Postgres |

Working memory is not a second live state. In JARVIS the task graph and `MissionResult` already
are the run's working state; a parallel mutable object would be one more thing to drift from them.

## Three rules the original did not have

### 1. Memory never feeds back into a run

Memory is written after a run finishes (`registry._run`, after the run row) and read only by the
API, for people. A run that silently used facts from an earlier run could not be reconstructed
from its own events (invariant 4), and its evaluation numbers would depend on the order scenarios
ran in. `tests/unit/test_memory_boundary.py` checks the source: no module in `orchestration`,
`intelligence`, `tools`, `llm`, `security`, `evaluation` or `integrations` imports `app.memory`,
and only `api/registry.py` and `api/v1/memory.py` do.

Using memory during a run would be a separate, opt-in, measured feature. It is not built.

### 2. Only verified findings become facts

A knowledge claim or relationship becomes a fact only when a finding that **passed verification**
cites the line it was read from - the same matching the evidence trail uses. Ungrounded claims
(a value the model wrote that is not on its line) never become facts, cited or not. Member 4 had
no gate: distilling unverified claims into durable memory would make a hallucination permanent.

Episodes are the opposite: **every** finding is logged, with its status, rejected ones included. A
memory of only what passed would make past investigations look better than they were.

### 3. No asserted confidence

Member 4 stored `confidence=1.0` on every fact. The project's rule is that confidence is computed,
never asserted, so a fact carries its support instead: which runs asserted it and from which lines.
`support_count` is the number of distinct (run, line) pairs. A reader judges from that.

`support_count` and `runs` are properties of `Fact`, not computed fields (`schemas.md`, decision 5:
a computed field would make the model reject its own JSON). The API returns them as fields through
`FactView`. A round-trip test holds this.

## Where facts live, and why not "wherever is up"

Semantic memory has one protocol (`app/memory/semantic.py:SemanticMemory`) and two stores, held to
one test suite (`tests/integration/test_memory.py`), as the knowledge base is (ADR-010):

- `GRAPH_STORE=neo4j` (the default, decision D2): `Neo4jSemanticMemory` in `neo4j_store.py`, the
  only module that imports the driver.
- `GRAPH_STORE=memory`: `PostgresSemanticMemory`, tables `memory_entities`, `memory_entity_runs`,
  `memory_facts`, `memory_fact_support`.

**The store is chosen by configuration, never by availability.** Falling back to Postgres when
Neo4j is down would split memory across two stores and answer differently depending on which was
up when each run finished. When the configured store is down, semantic memory is off for that run
and the log says so (`memory_recorded semantic=False`).

### The Neo4j model

```
(:KnownEntity {key, name, types, aliases, runs})
(:Fact {fact_id, kind, subject, subject_key, predicate, object, object_key, support})
(:KnownEntity)-[:ASSERTS]->(:Fact)-[:ABOUT]->(:KnownEntity)        ABOUT for relations only
```

These nodes are **not** scoped by run: they are the one place runs meet, and the per-run graph
(`:Entity`, `:Claim`, ...) never reads them. `support` is a list of `run_id<TAB>source` strings merged
without duplicates, so recording a run twice changes nothing. A fact's id is a hash of kind,
normalised subject, normalised predicate and normalised object, so the same statement from two
runs is one fact.

## Optional, and never failing a run

Same rules as run persistence and the graph store:

- Episodic memory needs Postgres; semantic memory needs its configured store. Whatever is missing,
  the run proceeds; `memory_recorded` logs what was and was not stored.
- Every write is contained (`memory_episodic_failed`, `memory_semantic_failed`), and the registry
  wraps the whole call (`memory_record_failed`), so even a bug in distillation cannot fail a run.
- The API answers 503 `MEMORY_UNAVAILABLE` for a tier whose store is unreachable, so "no memory of
  this" (404 `MEMORY_NOT_FOUND`) and "memory is off" are distinguishable.

Memory is written only for missions run through the API. `python -m app.cli investigate` stores
no run rows, so it records no memory.

## Forgetting a run

`SemanticMemory.forget(run_id)` removes a run's support and its "seen in", then drops facts nothing
supports and entities nothing references; `EpisodicMemory.forget(run_id)` removes its episodes and
archived snapshot. In Postgres, deleting a run row cascades through all of them. Exposed as
`DELETE /api/v1/memory/runs/{run_id}` and the Memory page's "forget this mission" (2026-10-05).

## What was measured (2026-10-05)

Three real missions on `qwen3:4b` over overlapping Aurora documents (dev log, Phase 33):

- "Project Aurora" became one known entity seen in all three, and the explorer's pop-up for it in
  the third mission says "seen in 2 earlier missions".
- After a repeat of the first mission, `PROJECT AURORA approved_budget INR 380,000` had support 2:
  two missions citing `aurora_financial_report.txt:r15`.
- **The limitation this exposed:** the same line `r12` gave two facts, `latest_completion_date` and
  `latest_completion_milestone`, because the model named the attribute differently in each run.
  Memory does not merge attribute synonyms; guessing that two names mean one thing would be the
  kind of unmarked inference the project avoids. Support therefore accumulates only when extraction
  is consistent, and a low count can mean "phrased differently", not "seen once".
