"""One turn of the investigation conversation (v4 Phase 3, streamed and editable in Phase 4).

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

**Streaming (Phase 4).** Given `emit`, a turn reports as it goes: what it is doing in plain words
(never the model's thinking), the answer's words as soon as the model has written them, and each
claim's mark the moment its check is done. Words arrive before marks, and a person sees which is
which: an unmarked claim is still being checked.

**Regenerate and edit (Phase 4).** An answer can be asked again, and a message edited; what they
replace is kept, marked superseded, so earlier versions can be compared and nothing is lost. The
history the model reads skips superseded turns.
"""

from __future__ import annotations

import asyncio
import re
import secrets
from collections.abc import Awaitable, Callable
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

Emit = Callable[[dict[str, Any]], Awaitable[None]] | None

MAX_TOOL_CALLS = 5
HISTORY_TURNS = 8
# Documents up to this size go into every step whole; larger cases are read through the tools.
WHOLE_TOKENS = 4000
# Words per streamed chunk, and the pause between chunks: a reading pace, not a delay.
WORDS_PER_CHUNK = 3
CHUNK_PAUSE_S = 0.03
_REFERENCE = re.compile(r"\b(?:run_[0-9a-f]{12}/)?F-\d{3,}\b")
_RECHECK = re.compile(
    r"\b(re-?check|re-?verify|check (?:it |them )?again|verify (?:it )?again)\b", re.I
)
_ONLY_RECHECK = re.compile(
    r"^\s*(please\s+)?(re-?check|re-?verify)\b[\s,]*((?:run_[0-9a-f]{12}/)?F-\d{3,}[\s,and]*)+\.?\s*$",
    re.I,
)
_DOING = {
    "search_evidence": "Searching the case for {query!r}",
    "read_span": "Reading {document}, lines {start}-{end}",
    "query_findings": "Looking up the findings about {text!r}",
    "calculate": "Calculating {expression}",
    "compare_values": "Comparing {a} with {b}",
}


class AnswerClaim(JarvisModel):
    text: str
    citations: list[str] = Field(default_factory=list)


class Step(JarvisModel):
    """One action of the loop, as the model returns it."""

    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    claims: list[AnswerClaim] = Field(default_factory=list)
    question: str = ""


class TurnNotFoundError(LookupError):
    pass


def _turn_id() -> str:
    return f"T-{secrets.token_hex(4)}"


async def _say(emit: Emit, event: dict[str, Any]) -> None:
    if emit is not None:
        await emit(event)


def _live(turns: list[Turn]) -> list[Turn]:
    return [t for t in turns if not t.superseded]


# --- the three ways a turn starts ---------------------------------------------------------------


async def converse(
    case_id: str,
    message: str,
    provider: LLMProvider,
    *,
    actor: str = "",
    emit: Emit = None,
    language: str = "",
) -> Thread:
    """Take the person's message, answer it, and return the thread with both turns added.
    `language` is the language the person chose ("" to detect it from the message)."""
    async with store.lock(case_id):
        thread = store.load(case_id)
        user = _user_turn(message, actor)
        history = _live(thread.turns)
        await _in_english(case_id, user, language, provider, emit)
        thread.turns.append(user)
        thread.turns.append(
            await _in_their_language(
                case_id, user, await _answer(case_id, user, history, provider, emit), emit
            )
        )
        store.save(thread)
        return thread


async def regenerate(
    case_id: str, turn_id: str, provider: LLMProvider, *, emit: Emit = None
) -> Thread:
    """Answer the same message again. The earlier answer stays, superseded, beside the new one."""
    async with store.lock(case_id):
        thread = store.load(case_id)
        index = _index(thread, turn_id, "assistant")
        user = next(
            (t for t in reversed(thread.turns[:index]) if t.role == "user" and not t.superseded),
            None,
        )
        if user is None:
            raise TurnNotFoundError(f"no message before {turn_id}")
        old = thread.turns[index]
        old.superseded = True
        history = _live(thread.turns[: thread.turns.index(user)])
        new = await _in_their_language(
            case_id, user, await _answer(case_id, user, history, provider, emit), emit
        )
        new.replaces = old.turn_id
        thread.turns.insert(index + 1, new)
        store.save(thread)
        return thread


async def edit(
    case_id: str,
    turn_id: str,
    text: str,
    provider: LLMProvider,
    *,
    emit: Emit = None,
    language: str = "",
) -> Thread:
    """Edit a message: the conversation branches there. The old message and everything after it
    stay, superseded; the edited message and its answer continue the thread."""
    async with store.lock(case_id):
        thread = store.load(case_id)
        index = _index(thread, turn_id, "user")
        history = _live(thread.turns[:index])
        for turn in thread.turns[index:]:
            turn.superseded = True
        user = _user_turn(text, thread.turns[index].actor)
        user.replaces = turn_id
        await _in_english(case_id, user, language, provider, emit)
        thread.turns.append(user)
        thread.turns.append(
            await _in_their_language(
                case_id, user, await _answer(case_id, user, history, provider, emit), emit
            )
        )
        store.save(thread)
        return thread


async def _in_english(
    case_id: str, user: Turn, language: str, provider: LLMProvider, emit: Emit
) -> None:
    """A message in an Indian language, read in English (v4 Phase 7, `language.py`)."""
    from app.conversation.language import read_in_english
    from app.language.evidence import needs_translation

    if not language and not needs_translation(user.text):
        return
    await _say(emit, {"type": "activity", "text": "Reading your question in English"})
    await read_in_english(user, language, await gather(case_id), provider)


async def _in_their_language(case_id: str, user: Turn, answer: Turn, emit: Emit) -> Turn:
    """The verified English answer, and its labelled translation into the person's language."""
    if user.language == "en":
        return answer
    from app.conversation.language import answer_in_their_language

    await _say(emit, {"type": "activity", "text": "Translating the verified answer"})
    await answer_in_their_language(answer, user.language, await gather(case_id))
    if answer.translation is not None:
        await _say(emit, {"type": "translation", **answer.translation.model_dump(mode="json")})
    return answer


def _user_turn(message: str, actor: str) -> Turn:
    return Turn(
        turn_id=_turn_id(),
        role="user",
        text=message,
        actor=actor,
        findings_referred=list(dict.fromkeys(_REFERENCE.findall(message))),
    )


def _index(thread: Thread, turn_id: str, role: str) -> int:
    for index, turn in enumerate(thread.turns):
        if turn.turn_id == turn_id and turn.role == role and not turn.superseded:
            return index
    raise TurnNotFoundError(f"no current {role} turn {turn_id}")


# --- answering -----------------------------------------------------------------------------------


async def _answer(
    case_id: str, user: Turn, history: list[Turn], provider: LLMProvider, emit: Emit
) -> Turn:
    material = await gather(case_id)
    await _say(
        emit,
        {
            "type": "activity",
            "text": f"Reading the case: {len(material.documents)} document(s), "
            f"{len(material.findings)} finding(s)",
        },
    )
    references = user.findings_referred
    rechecks: list[Recheck] = []
    if references and _RECHECK.search(user.text):
        await _say(emit, {"type": "activity", "text": f"Re-checking {', '.join(references)}"})
        rechecks = await recheck(material, references, provider)
    if rechecks and _ONLY_RECHECK.match(user.text):
        return Turn(
            turn_id=_turn_id(),
            role="assistant",
            text=_recheck_summary(rechecks),
            rechecks=rechecks,
            findings_referred=references,
            stop_reason=StopReason.RECHECKED,
        )
    assistant = await _loop(history, material, user.text, provider, emit)
    assistant.rechecks = rechecks
    assistant.findings_referred = references
    return assistant


async def _loop(
    history: list[Turn],
    material: CaseMaterial,
    message: str,
    provider: LLMProvider,
    emit: Emit = None,
) -> Turn:
    prompts = get_prompt_library()
    steps: list[ToolStep] = []
    final: Step | None = None
    stop = StopReason.FAILED
    for used in range(MAX_TOOL_CALLS + 1):
        prompt = prompts.get("conversation").render(
            case=_describe_case(material),
            history=_history(history),
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
            question = step.question.strip()
            await _stream_words(emit, 0, question or "I need more from you to go on.")
            return Turn(
                turn_id=_turn_id(),
                role="assistant",
                text=question or "I need more from you to go on.",
                question=question,
                steps=steps,
                stop_reason=StopReason.ASKED_USER,
            )
        if used == MAX_TOOL_CALLS:
            stop = StopReason.STEP_LIMIT
            break
        await _say(emit, {"type": "activity", "text": _doing(action, step.arguments)})
        steps.append(
            ToolStep(
                tool=action,
                arguments=step.arguments,
                result=run_tool(material, action, step.arguments),
            )
        )

    proposed = final.claims if final else []
    for index, claim in enumerate(proposed):
        await _stream_words(emit, index, claim.text)
    if proposed:
        await _say(emit, {"type": "activity", "text": f"Checking {len(proposed)} claim(s)"})
    claims = await verify_claims(proposed, material, provider, emit=emit)
    if not claims:
        text = (
            "I could not reach an answer I can cite within this turn's tool budget."
            if stop is StopReason.STEP_LIMIT
            else "I could not produce an answer this turn."
            if stop is StopReason.FAILED
            else "The case's documents do not answer that."
        )
        await _stream_words(emit, 0, text)
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


def _doing(tool: str, arguments: dict[str, Any]) -> str:
    """What a tool call is doing, in words - formatted defensively: the model chose the values."""
    template = _DOING.get(tool)
    if template is None:
        return f"Trying {tool}"
    try:
        return template.format(**{k: str(v)[:80] for k, v in arguments.items()})
    except (KeyError, IndexError, ValueError):
        return template.split(" {", 1)[0]


async def _stream_words(emit: Emit, claim: int, text: str) -> None:
    if emit is None:
        return
    words = text.split()
    for start in range(0, len(words), WORDS_PER_CHUNK):
        chunk = " ".join(words[start : start + WORDS_PER_CHUNK])
        await emit({"type": "words", "claim": claim, "text": chunk + " "})
        await asyncio.sleep(CHUNK_PAUSE_S)


async def verify_claims(
    claims: list[AnswerClaim],
    material: CaseMaterial,
    provider: LLMProvider,
    *,
    emit: Emit = None,
) -> list[AnsweredClaim]:
    verifier = build_verification_provider(provider)
    whole = whole_documents(material.documents, task_id="task_001", budget_tokens=10**9)
    out: list[AnsweredClaim] = []
    for index, claim in enumerate(claims):
        text = claim.text.strip()
        if not text:
            continue
        cited = [c.strip() for c in claim.citations if material.line(c.strip()) is not None]
        if not cited and whole is not None:
            cited = cite_by_values(text, whole)
        if not cited:
            answered = AnsweredClaim(
                text=text,
                citations=claim.citations,
                issues=["cites no line of the case's documents"],
            )
        else:
            refs = []
            for number, locator in enumerate(cited, start=1):
                document, _, position = locator.rpartition(":")
                refs.append(
                    EvidenceRef(
                        evidence_id=f"E-{number:03d}",
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
            answered = AnsweredClaim(
                text=text,
                citations=cited,
                status=result.status.value,
                issues=[i.description for i in result.issues][:4],
            )
        out.append(answered)
        await _say(
            emit,
            {
                "type": "verdict",
                "claim": index,
                "status": answered.status,
                "citations": answered.citations,
            },
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


def _history(turns: list[Turn]) -> str:
    lines = []
    for turn in turns[-HISTORY_TURNS:]:
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
