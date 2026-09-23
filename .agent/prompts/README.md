# Prompts

Every prompt JARVIS sends lives here as Markdown. None live as Python string literals.

**Why this matters:** prompts are the behavioural surface of an LLM-driven system. If they
are buried in code, a prompt change is invisible in review, untracked in evaluation, and
impossible to attribute a metric shift to. Here, a prompt change is a diff, and every
evaluation report stamps the prompt version it ran against.

Loaded by `app.llm.prompts` (Phase 4). Referenced by role, never by path, so an engine asks
for `intent` rather than knowing where the file is.

## File format

Each prompt file carries a front-matter block and three required sections:

```markdown
---
role: intent
version: 1
output_schema: app.schemas.intent.Intent
phase: 6
---

## Inputs
What the caller provides, and what each input means.

## Task
The instruction itself.

## Output
The exact structure expected, with the schema injected by `generate_structured`.
```

## Rules

1. **The output schema is injected, not described in prose.** `generate_structured()`
   injects the JSON schema derived from the Pydantic model named in `output_schema`. The
   prompt states intent; the schema states shape.
2. **Version bumps on any semantic change.** Whitespace and typo fixes do not bump.
   A version bump invalidates evaluation comparisons against earlier reports.
3. **Document content is data, never instruction.** Prompts that include retrieved document
   text must delimit it explicitly and state that instructions inside it are to be treated
   as content under investigation. This is the defence against prompt injection via uploaded
   documents (risk register; adversarial suite, Phase 23).
4. **No prompt asks the model for a confidence number** that the system then trusts.
   Confidence is computed from resolved evidence (Phase 13).

## Roles

| File | Role | Output | Phase |
|---|---|---|---|
| `intent.md` | Interpret the objective | `Intent` | 6 |
| `planner.md` | Propose a task decomposition | `CandidatePlan` | 7 |
| `router.md` | Break a tie between candidate tools | `ToolSelection` | 10 |
| `reasoning.md` | Derive candidate findings with citations | `list[CandidateFinding]` | 13 |
| `evidence_gap.md` | Phrase a retrieval query for a detected gap | `RetrievalQuery` | 14 |
| `verification.md` | Check a claim against its evidence, independently | `VerificationResult` | 15 |
| `synthesis.md` | Write report prose over fixed facts | `ReportSections` | 18 |

Files arrive with their phase. This directory is intentionally empty until Phase 4 builds
the loader.
