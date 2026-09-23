# JARVIS — Project Overview

**One line:** JARVIS is an adaptive, evidence-driven AI orchestration engine that turns a
high-level objective into a verified, traceable investigation.

---

## The problem

Most AI assistants work like this:

```
User -> Prompt -> LLM -> Answer
```

For a question with an answer, that is the right shape. For a *task*, it is the wrong shape,
and no amount of prompt engineering fixes it.

Consider a real request:

> "Analyse these project documents, compare the financial information, identify
> contradictions in the timeline, determine which claims are supported by evidence, and give
> me a final report."

That is not one task. It is a dozen, with dependencies between them, and — critically — the
right sequence of steps cannot be known in advance, because it depends on what the earlier
steps find. You cannot plan the whole investigation up front because you do not yet know
what is in the documents.

A one-shot model responds to that request by producing something that *reads* like the
answer. It will be fluent. It will cite things. Some of the citations will be real. There is
no mechanism anywhere in that pipeline that distinguishes a conclusion the evidence supports
from a conclusion the model found plausible, and no mechanism that notices when the evidence
needed to decide simply is not there.

**The problem JARVIS addresses:**

> How can an AI system autonomously transform an ambiguous high-level objective into a
> controlled, multi-step, evidence-aware execution process — rather than generating a
> one-shot response?

---

## The answer: a closed cognitive loop

JARVIS does not answer. It investigates, and the loop is closed:

```
                    USER OBJECTIVE
                          |
     Intent  ->  Plan  ->  Task Graph  ->  Tool Routing
                          |
                      Execution
                          |
                     Observation
                          |
                      Reasoning
                          |
                  Candidate Findings
                          |
                     Verification
                       /       \
              SUPPORTED         NOT SUPPORTED
                    |                 |
                    |        What evidence is missing?
                    |                 |
                    |          Create a task to get it
                    |                 |
                    |            Execute, re-reason,
                    |              re-verify  --------+
                    |                                 |
                    +------------- <------------------+
                          |
                      Synthesis
                          |
                 EVIDENCE-BACKED REPORT
```

The feedback edge is the whole point. The plan is not sacred: when verification fails or new
information invalidates an assumption, the execution graph changes.

---

## What makes this an AI systems project rather than a wrapper

The interesting decisions are not in the prompts. They are in the seams around the model:

| The model proposes | The system decides |
|---|---|
| A task decomposition | Whether it is a legal DAG, whether it covers the intent, and how to repair it if not |
| A tool for a task | Which tools are even capable and schema-compatible — the model only breaks ties |
| Candidate findings with citations | Whether those citations resolve to real retrieved content |
| Its own confidence | Confidence, computed from resolved evidence — the model's self-report is not trusted |
| That evidence is thin | Which specific element is unsupported, and what task would obtain it |

An LLM sits inside the system as one component. It is not the architecture (ADR-004).

---

## The three features that carry the project

**1. Adaptive evidence gap detection.** When support is insufficient, JARVIS names the
specific missing element — *"the approved baseline completion date"* — and creates a task to
retrieve it. This is meaningfully different from "I'm not certain." The system identifies
what information would reduce its uncertainty, then goes and gets it.

**2. Closed-loop replanning.** The initial plan is a hypothesis about how to proceed. When a
task fails permanently, or verification rejects a finding, or new evidence invalidates an
assumption, the task graph is revised mid-run and execution continues. Bounded, with every
stop condition recorded.

**3. Evidence- and confidence-aware findings.** Every conclusion carries its claim,
classification (`FACT` / `INFERENCE` / `HYPOTHESIS` / `UNKNOWN`), the evidence supporting it
with exact source locators, its verification status, and a computed confidence. The final
report shows rejected findings alongside verified ones, because a report that only shows
what survived is not an audit.

---

## The MVP domain: evidence-based investigation

One domain, done properly: investigating a set of heterogeneous documents for
inconsistencies, contradictions and unsupported claims.

> "Find inconsistencies between the project timeline and budget, and explain the possible
> impact."

The user does not specify the steps. Working out the steps is the agent's job — that is what
the agent is *for*.

---

## How success is judged

Not by "does the LLM answer?" By:

- Can it decompose a complex objective autonomously?
- Is the dependency graph it builds valid?
- Does it choose appropriate tools?
- Does it recover from failures?
- Does it identify evidence gaps?
- Does it replan when the plan stops being right?
- Does it distinguish facts from hypotheses?
- Does it verify its own findings?
- Can it explain where every finding came from?
- Is the entire execution traceable?
- **Can all of that be measured?**

The last one is why the evaluation harness (Phase 20) is a larger part of the contribution
than the user interface. A behaviour that cannot be measured is a claim, not a result.

---

## Member 1's contribution

The cognitive control loop: objective in, verified action out. See
[`member-1-scope.md`](member-1-scope.md) for the precise boundary — including what is
explicitly *not* in scope.
