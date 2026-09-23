# ADR-004 — Custom orchestration, not an agent framework

## Status

Accepted — 2026-09-23 (Phase 1)

## Context

LangGraph, CrewAI, AutoGen and LlamaIndex all provide agent orchestration: task graphs,
tool calling, state management, retries. Using one would remove a large amount of the code
this project plans to write.

The question is what that code *is*. For JARVIS, the orchestration layer is not plumbing on
the way to the interesting part — it **is** the interesting part. The contribution is
specifically:

- a planner whose output is validated into a legal DAG by application code
- a router that filters deterministically before consulting a model
- an evidence binder that decides which citations count
- confidence computed from resolved evidence rather than self-reported
- gap detection that names a specific missing element
- a replanning loop that mutates the graph mid-run, with recorded termination reasons
- an evaluation harness that measures every one of those

A framework would own exactly the layer the project is supposed to be about.

## Decision

Build the orchestration engine directly, on asyncio, Pydantic and SQLAlchemy.

No agent framework. Libraries are used for what libraries are good at — HTTP, validation,
persistence, PDF parsing — and not for the cognitive loop.

## Reason

**1. The differentiators do not fit the frameworks' grain.**
Frameworks model agent loops as graphs of nodes with state. JARVIS needs a graph the
*agent itself edits mid-execution*, in response to verification outcomes, where each
mutation is versioned and every insertion is attributable to a specific evidence gap.
That is expressible in a framework only by fighting it.

**2. Evaluation needs total instrumentation.**
Every metric in Phase 20 — plan validity before repair, repair counts, routing mode
(deterministic vs. LLM tiebreak), citation resolution rate, per-iteration confidence gain —
depends on observing internal decisions that a framework does not expose, because no
framework anticipated wanting them.

**3. "I used a framework" is not a contribution.**
The project has to answer, to a panel, what was engineered. "The planner produces a
candidate decomposition which is then validated into a DAG by a cycle detector and intent
coverage checker, with deterministic repair before re-prompting" is an answer. "LangGraph
handled orchestration" is not.

**4. Frameworks hide the failure modes worth studying.**
When a small local model emits a plan with a dependency cycle, that is interesting: it needs
detection, repair, a bounded re-prompt, and a clean failure if it persists. A framework that
silently smooths it over removes both the problem and the learning.

**5. The scope is genuinely bounded.**
This is not rebuilding LangGraph. It is a task graph, a scheduler, a router, and a loop —
a few thousand lines, all of it load-bearing for the contribution.

## Consequences

**Accepted costs**

- More code to write, test and maintain: task graph, scheduler, retry, structured-output
  repair, state machine. Roughly Phases 4, 7, 8, 10 and 11.
- No community-provided integrations. Tools are written by hand — acceptable, as the tool
  set is deliberately small and domain-specific.
- Bugs a mature framework has already fixed will be discovered here. Mitigated by the
  adversarial test suite (Phase 23) and property-style tests on graph readiness.

**Gained**

- Full control over, and full visibility into, every decision the agent makes
- Evaluation can instrument anything, because nothing is hidden
- No dependency on a fast-moving framework's breaking changes
- The architecture can be explained end to end, which matters for a project that will be
  defended in front of people who ask questions

## What is explicitly not rejected

Libraries for non-cognitive work remain welcome: FastAPI, Pydantic, SQLAlchemy, httpx,
pypdf, pgvector. The boundary is that **nothing external owns a decision the agent makes.**

## Revisit if

The project moves past MVP and needs capabilities that are genuinely commodity — multi-agent
negotiation protocols, distributed task queues, a broad third-party tool ecosystem. None of
those are in scope here.
