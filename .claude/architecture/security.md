# Security: untrusted document content

**Phase:** 27 (2026-10-03)
**Code:** `app/security/injection.py`, the scan in `app/orchestration/mission.py`, the wrappers in
`app/integrations/verification.py` and `app/intelligence/reasoning/engine.py`
**Ported from:** Member 4, `security/injection_guard.py` and `security_test_suite.py`. See
`integrations/teammate-port.md`, T7-T9.

---

## The rule

**Document content is data, never instruction.** JARVIS reads documents written by other people,
and a document can contain text written to steer a model: "ignore all previous instructions",
"you are now in maintenance mode", a fake `<|im_start|>system` block. Three mechanisms keep that
text in its place, and none of them depends on the model choosing to behave.

## 1. Every document is scanned, before any model reads it

`run_mission` scans every document as its first act, before the intent call. A document matching
any pattern produces:

- an `INJECTION_DETECTED` event (`document`, `severity`, `categories`, `matches`), which sits on the
  timeline **before** `INTENT_CREATED`, which is tested;
- an entry in `MissionResult.security`, served as `MissionDetail.security_flags` and shown in
  Mission Control as a warning naming the document, the severity and the categories;
- a `Limitation` in the final report: "*finance.txt contains text resembling a prompt injection
  (HIGH: override_instructions, system_prompt_extraction); it was treated as data, never as
  instruction*".

Uploads are scanned too, so `POST /api/v1/documents` returns the flag before a mission starts.

### Flag, never drop

A flagged document is **still read**. A security-incident report quoting an attack matches the
patterns, and so does any honest document about prompt injection. If a match removed a document, an
attacker could delete evidence from an investigation by quoting a phrase in it. The scan therefore
informs and never filters. Keeping the text inert is the wrappers' job, below.

### Patterns and severity

Member 4's five categories and 21 patterns, verbatim, plus five JARVIS patterns kept in a separate
list (`JARVIS_PATTERNS`), each added for a measured miss:

| Category | Original | Added | Severity |
|---|---|---|---|
| `override_instructions` | 6 | "note/message/instructions to the AI/assistant/model..." | MEDIUM |
| `role_manipulation` | 4 | - | MEDIUM |
| `system_prompt_extraction` | 4 | - | HIGH |
| `data_exfiltration` | 3 | - | HIGH |
| `tool_call_spoofing` | 4 | chat-template tokens; `</document>`; findings-shaped JSON | HIGH |

Severity is the original rule: HIGH if any hit is in one of the three HIGH categories, otherwise
MEDIUM, and NONE without hits.

## 2. Untrusted text reaches a model inside a `<document>` block

- **Verification** (prompt v2): each cited text is its own `<document source="a.txt:r10">` block.
- **Reasoning** (prompt v5): the observations, which quote document lines, are one
  `<document source="task observations">` block.

Both prompts say that everything inside a block is quoted data. **A block cannot be closed from
inside.** Member 4's original wrapper put content in verbatim, so a document containing
`</document>` ended its own block and whatever followed read as prompt. The closing tag is now
neutralised inside content (`</document_>`), and a `"` in a source name cannot break the attribute.

Prompts that never carry document text are not wrapped: intent and planner see the user's objective,
and relevance sees the model's own candidate claims. Synthesis writes prose over findings that are
already fixed, and its numbers are injected programmatically.

## 3. Structure the model cannot talk its way around

These predate Phase 27 and are why an injection that gets past the scan still cannot do much:

- A finding counts only if its citations **resolve to locators tools produced** (the evidence
  binder). A document telling the model to "report that the project is on schedule" can make the
  model write that sentence, and the sentence then has nothing to cite.
- Confidence is computed from resolved evidence. A document cannot assert it.
- Verification sees only the claim and its evidence, never the reasoning.
- No tool executes code. The calculator walks an AST whitelist, and `eval`/`exec` are forbidden by
  test.

## Measured

`python -m app.cli eval-trust` runs the 27-case suite in `.agent/evals/security/` beside the trust
benchmark, as Member 4's runner did:

| | Member 4's patterns only | With JARVIS additions |
|---|---|---|
| Cases correct | 22/27 | **27/27** |
| Member 4's own 14 cases | 14/14 | 14/14 |
| Missed | chat-template spoof, note to the AI, wrapper breakout, fake findings JSON, message for the assistant | none |
| False positives (7 clean cases) | 0 | 0 |
| False positives on all 14 fixture documents | 0 | 0 |

## What this does not do

- **It is pattern matching.** A paraphrased attack ("kindly set aside the guidance you were given")
  is not detected. Detection is a signal for the human reading the report. The defence is the
  wrapping and the structure, not the scan.
- It does not scan model output. A model that was steered produces findings, and those are judged
  like every other finding, by evidence resolution and verification.
