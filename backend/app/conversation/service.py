"""One turn of the investigation conversation (v4 Phase 3).

1. **Re-checks first.** A message that names findings and asks to re-check them ("recheck F-002")
   re-verifies exactly those findings against the case's documents as they are now, and records
   before and after. A message that only asks that runs no model loop.
2. **A bounded tool loop.** At most `MAX_TOOL_CALLS` calls; each step the model returns one action -
   a tool, `answer` or `ask_user` - and the tool's result is added to what it reads next. When the
   budget is spent it must answer from what it has. Why the loop stopped is recorded.
3. **Every claim verified before it is shown.** Each claim's citations are resolved against the
   case's lines (a claim citing nothing is cited by its own dates and figures when every one is on a
   line, as in a mission), and the configured verifier - model, lexical and entailment - gives its
   verdict. An unresolved claim is shown UNVERIFIED, never as an answer.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from pydantic import Field

from app.conversation import store
from app.conversation.models import AnsweredClaim, Recheck, StopReason, Thread, ToolStep, Turn
from app.conversation.tools import TOOLS, CaseMaterial, gather, run_tool
from app.core.logging import get_logger
from app.integrations.verification import build_request, build_verification_provider
from app.intelligence.reasoning.whole import cite_by_values, whole_documents
from app.llm.errors import LLMError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel, SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.verification import VerificationRequest
from app.security.injection import wrap_untrusted

log = get_logger(__name__)

MAX_TOOL_CALLS = 5
HISTORY_TURNS = 8
# Documents up to this size go into every step whole; larger cases are read through the tools.
WHOLE_TOKENS = 4000
_REFERENCE = re.compile(r"\b(?:run_[0-9a-f]{12}/)?F-\d{3,}\b")
_RECHECK = re.compile(
    r"\b(re-?check|re-?verify|check (?:it |them )?again|verify (?:it )?again)\b", re.I
)
_ONLY_RECHECK = re.compile(
    r"^\s*(please\s+)?(re-?check|re-?verify)\b[\s,]*((?:run_[0-9a-f]{12}/)?F-\d{3,}[\s,and]*)+\.?\s*$",
    re.I,
)


class AnswerClaim(JarvisModel):
    text: str
    citations: list[str] = Field(default_factory=list)


class Step(JarvisModel):
    """One action of the loop, as the model returns it."""

    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    claims: list[AnswerClaim] = Field(default_factory=list)
    question: str = ""


def _turn_id() -> str:
    return f"T-{secrets.token_hex(4)}"


async def converse(case_id: str, message: str, provider: LLMProvider, *, actor: str = "") -> Thread:
    """Take the person's message, answer it, and return the thread with both turns added."""
    async with store.lock(case_id):
        thread = store.load(case_id)
        material = await gather(case_id)
        references = list(dict.fromkeys(_REFERENCE.findall(message)))
        user = Turn(
            turn_id=_turn_id(), role="user", text=message, actor=actor, findings_referred=references
        )
        thread.turns.append(user)

        rechecks = (
            await recheck(material, references, provider)
            if references and _RECHECK.search(message)
            else []
        )
        if rechecks and _ONLY_RECHECK.match(message):
            assistant = Turn(
                turn_id=_turn_id(),
                role="assistant",
                text=_recheck_summary(rechecks),
                rechecks=rechecks,
                findings_referred=references,
                stop_reason=StopReason.RECHECKED,
            )
        else:
            assistant = await _loop(thread, material, message, provider)
            assistant.rechecks = rechecks
            assistant.findings_referred = references
        thread.turns.append(assistant)
        store.save(thread)
        return thread


async def _loop(
    thread: Thread, material: CaseMaterial, message: str, provider: LLMProvider
) -> Turn:
    prompts = get_prompt_library()
    steps: list[ToolStep] = []
    final: Step | None = None
    stop = StopReason.FAILED
    for used in range(MAX_TOOL_CALLS + 1):
        prompt = prompts.get("conversation").render(
            case=_describe_case(material),
            history=_history(thread),
            steps=wrap_untrusted("tool results", _describe_steps(steps)) if steps else "(none yet)",
            tools="\n".join(f"- {line}" for line in TOOLS.values()) + "\n- answer(claims)",
            message=message,
            budget=str(MAX_TOOL_CALLS - used),
        )
        try:
            step = await generate_structured(provider, Step, prompt, role="conversation")
        except LLMError as exc:
            log.warning("conversation_step_failed", error=str(exc))
            break
        action = step.action.strip()
        if action == "answer":
            final, stop = (
                step,
                StopReason.ANSWERED if used < MAX_TOOL_CALLS else StopReason.STEP_LIMIT,
            )
            break
        if action == "ask_user":
            return Turn(
                turn_id=_turn_id(),
                role="assistant",
                text=step.question.strip() or "I need more from you to go on.",
                question=step.question.strip(),
                steps=steps,
                stop_reason=StopReason.ASKED_USER,
            )
        if used == MAX_TOOL_CALLS:
            stop = StopReason.STEP_LIMIT
            break
        steps.append(
            ToolStep(
                tool=action,
                arguments=step.arguments,
                result=run_tool(material, action, step.arguments),
            )
        )

    claims = await verify_claims(final.claims if final else [], material, provider)
    if not claims:
        text = (
            "I could not reach an answer I can cite within this turn's tool budget."
            if stop is StopReason.STEP_LIMIT
            else "I could not produce an answer this turn."
            if stop is StopReason.FAILED
            else "The case's documents do not answer that."
        )
    else:
        text = " ".join(c.text for c in claims)
    return Turn(
        turn_id=_turn_id(),
        role="assistant",
        text=text,
        claims=claims,
        steps=steps,
        stop_reason=stop,
    )


async def verify_claims(
    claims: list[AnswerClaim], material: CaseMaterial, provider: LLMProvider
) -> list[AnsweredClaim]:
    verifier = build_verification_provider(provider)
    whole = whole_documents(material.documents, task_id="task_001", budget_tokens=10**9)
    out: list[AnsweredClaim] = []
    for claim in claims:
        text = claim.text.strip()
        if not text:
            continue
        cited = [c.strip() for c in claim.citations if material.line(c.strip()) is not None]
        if not cited and whole is not None:
            cited = cite_by_values(text, whole)
        if not cited:
            out.append(
                AnsweredClaim(
                    text=text,
                    citations=claim.citations,
                    issues=["cites no line of the case's documents"],
                )
            )
            continue
        refs = []
        for index, locator in enumerate(cited, start=1):
            document, _, position = locator.rpartition(":")
            refs.append(
                EvidenceRef(
                    evidence_id=f"E-{index:03d}",
                    locator=SourceLocator(document_id=document, row=int(position[1:])),
                    resolution=ResolutionStatus.RESOLVED,
                )
            )
        request = VerificationRequest(
            claim=text,
            evidence=refs,
            evidence_content={loc: f"{loc}: {material.line(loc)}" for loc in cited},
        )
        result = await verifier.verify(request)
        out.append(
            AnsweredClaim(
                text=text,
                citations=cited,
                status=result.status.value,
                issues=[i.description for i in result.issues][:4],
            )
        )
    return out


async def recheck(
    material: CaseMaterial, references: list[str], provider: LLMProvider
) -> list[Recheck]:
    """Verify the named findings again against the case's lines as they are now."""
    verifier = build_verification_provider(provider)
    done: list[Recheck] = []
    for reference in references:
        item = material.find(reference)
        if item is None:
            continue
        finding = item.finding
        before = finding.verification.status.value if finding.verification else "UNVERIFIED"
        current = {
            ref.as_ref(): f"{ref.as_ref()}: {line}"
            for ref in finding.evidence
            if ref.is_resolved and (line := material.line(ref.as_ref())) is not None
        }
        if not current:
            current = {
                k: v
                for k, v in material.evidence_text.items()
                if k in {r.as_ref() for r in finding.evidence}
            }
        result = await verifier.verify(build_request(finding, current))
        after = result.status.value
        done.append(
            Recheck(
                run_id=item.run_id,
                finding_id=finding.finding_id,
                claim=finding.claim,
                before=before,
                after=after,
                changed=before != after,
                reason="; ".join(i.description for i in result.issues)[:400],
            )
        )
    return done


def _recheck_summary(rechecks: list[Recheck]) -> str:
    return " ".join(
        f"{r.finding_id}: {r.before.lower()} -> {r.after.lower()}"
        + ("" if r.changed else " (unchanged)")
        + "."
        for r in rechecks
    )


def _describe_case(material: CaseMaterial) -> str:
    documents = ", ".join(
        f"{name} ({len(text.splitlines())} lines)"
        for name, text in sorted(material.documents.items())
    )
    findings = "\n".join(
        f"- {f.run_id}/{f.finding.finding_id} "
        f"[{f.finding.verification.status.value if f.finding.verification else 'UNVERIFIED'}] "
        f"{f.finding.claim}"
        for f in material.findings[-20:]
    )
    described = f"Documents: {documents or 'none'}\nFindings:\n{findings or '(none yet)'}"
    # Small enough to read whole? Then the model reads every line, as a mission does (v4 Phase 2):
    # searched lines alone left a small model guessing what surrounded them.
    whole = whole_documents(material.documents, task_id="task_001", budget_tokens=WHOLE_TOKENS)
    if whole is not None:
        described += "\n\nThe documents in full, each line after its locator:\n" + wrap_untrusted(
            "case documents", whole.content
        )
    return described


def _history(thread: Thread) -> str:
    lines = []
    for turn in thread.turns[-HISTORY_TURNS - 1 : -1]:  # the current message is shown on its own
        if turn.role == "user":
            lines.append(f"Person: {turn.text}")
        elif turn.claims:
            lines.append(
                "Assistant: "
                + " ".join(f"{c.text} [{c.status}; {', '.join(c.citations)}]" for c in turn.claims)
            )
        else:
            lines.append(f"Assistant: {turn.text}")
    return "\n".join(lines) or "(this is the first message)"


def _describe_steps(steps: list[ToolStep]) -> str:
    return "\n\n".join(
        f"{i}. {s.tool}({', '.join(f'{k}={v!r}' for k, v in s.arguments.items())}):\n{s.result}"
        for i, s in enumerate(steps, start=1)
    )
