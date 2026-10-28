"""Proof (Phase U7): the verification receipt, and the same question put to the plain model.

**The receipt** is what a reader needs to trust a report without trusting the software: which
model and prompt versions ran, a SHA-256 of each file as it was read, every finding with its
verification and how many of its citations resolved, and how each sentence of the answer fared
against the files. It is hashed over its own canonical JSON, so a printed receipt can be checked
against the run later. Everything in it is counted from the run; nothing is generated.

**The comparison** puts the same question and the same files to the same model in one plain
prompt - no plan, no reading strategy, no verification - and scores both answers with the same
sentence checker (`check_narrative`, Member 4's evaluator) against the same evidence: every
non-blank line of every file. Neither side is judged by a model. The baseline prompt is a fair
one: it asks for an answer grounded in the documents, which is what a careful person would type.

The prompt lives here rather than in `.agent/prompts/`: the library's versions key the evaluation
trend series, and a prompt the pipeline never runs must not split them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import Field

from app.intelligence.synthesis.grounding import check_narrative
from app.llm.provider import CompletionRequest, LLMProvider
from app.schemas.common import JarvisModel, utcnow
from app.schemas.finding import Finding
from app.schemas.language import DocumentLanguage
from app.schemas.result import FinalReport, NarrativeCheck, SectionKind
from app.schemas.trust import EvidenceText, TrustStatus

BASELINE_PROMPT_VERSION = 1

_BASELINE_PROMPT = """You are given documents and a question.
Answer the question using the documents. Be specific: state the dates, figures and names
that matter, and say which document says what.
If the documents do not answer the question, say so.

{documents}

Question: {question}

Reply as JSON: {{"answer": "<the answer, one paragraph>"}}"""

# A long file set would not fit a small model's context; the plain model sees at most this much,
# and the comparison says so when it was cut.
MAX_BASELINE_CHARS = 24_000


# --- the receipt ---------------------------------------------------------------------------------


class ReceiptDocument(JarvisModel):
    name: str
    sha256: str
    characters: int
    evidence_id: str = ""


class ReceiptLanguage(JarvisModel):
    """A document read through a translation (v4 Phase 6): what translated it, and how much."""

    name: str
    language: str
    engine: str
    engine_version: str
    translated_lines: int
    unsafe_lines: int = 0


class ReceiptFinding(JarvisModel):
    finding_id: str
    claim: str
    classification: str
    verification: str
    verifier: str = ""
    degraded: bool = False
    confidence: float
    citations: int
    citations_resolved: int


class ReceiptAnswer(JarvisModel):
    sentences: int = 0
    supported: int = 0
    partial: int = 0
    unsupported: int = 0
    contradicted: int = 0
    insufficient: int = 0


class Receipt(JarvisModel):
    run_id: str
    question: str
    model: str
    prompt_versions: dict[str, int] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    documents: list[ReceiptDocument] = Field(default_factory=list)
    findings: list[ReceiptFinding] = Field(default_factory=list)
    answer: ReceiptAnswer = Field(default_factory=ReceiptAnswer)
    tasks_planned: int = 0
    tasks_completed: int = 0
    gaps_open: int = 0
    # Documents read in translation and the engine that translated each (v4 Phase 6). Left out of
    # the hash when empty, so an English-only receipt hashes as it did before.
    languages: list[ReceiptLanguage] = Field(default_factory=list)
    # SHA-256 over the canonical JSON of every field above.
    receipt_hash: str = ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tally(check: NarrativeCheck | None) -> ReceiptAnswer:
    if check is None:
        return ReceiptAnswer()
    statuses = [s.status for s in check.sentences]
    return ReceiptAnswer(
        sentences=len(statuses),
        supported=statuses.count(TrustStatus.SUPPORTED),
        partial=statuses.count(TrustStatus.PARTIALLY_SUPPORTED),
        unsupported=statuses.count(TrustStatus.UNSUPPORTED),
        contradicted=statuses.count(TrustStatus.CONTRADICTED),
        insufficient=statuses.count(TrustStatus.INSUFFICIENT_EVIDENCE),
    )


def summary_check(report: FinalReport | None) -> NarrativeCheck | None:
    if report is None:
        return None
    return next(
        (c for c in report.narrative_checks if c.section is SectionKind.EXECUTIVE_SUMMARY), None
    )


def summary_text(report: FinalReport | None) -> str:
    if report is None:
        return ""
    section = next((s for s in report.sections if s.kind is SectionKind.EXECUTIVE_SUMMARY), None)
    return section.narrative.strip() if section else ""


def build_receipt(
    *,
    run_id: str,
    question: str,
    model: str,
    prompt_versions: dict[str, int],
    started_at: datetime | None,
    finished_at: datetime | None,
    texts: dict[str, str],
    evidence: dict[str, str],
    findings: list[Finding],
    report: FinalReport | None,
    tasks_planned: int,
    tasks_completed: int,
    gaps_open: int,
    languages: dict[str, DocumentLanguage] | None = None,
) -> Receipt:
    receipt = Receipt(
        run_id=run_id,
        question=question,
        model=model,
        prompt_versions=dict(sorted(prompt_versions.items())),
        started_at=started_at,
        finished_at=finished_at,
        documents=[
            ReceiptDocument(
                name=name,
                sha256=_sha256(text),
                characters=len(text),
                evidence_id=evidence.get(name, ""),
            )
            for name, text in sorted(texts.items())
        ],
        findings=[
            ReceiptFinding(
                finding_id=f.finding_id,
                claim=f.claim,
                classification=f.classification.value,
                verification=f.verification.status.value if f.verification else "NOT_VERIFIED",
                verifier=f.verification.verifier if f.verification else "",
                degraded=f.verification.degraded if f.verification else False,
                confidence=round(f.confidence.value, 4),
                citations=len(f.evidence),
                citations_resolved=sum(1 for e in f.evidence if e.is_resolved),
            )
            for f in findings
        ],
        answer=tally(summary_check(report)),
        tasks_planned=tasks_planned,
        tasks_completed=tasks_completed,
        gaps_open=gaps_open,
        languages=[
            ReceiptLanguage(
                name=name,
                language=reading.language,
                engine=reading.engine or "not translated",
                engine_version=reading.engine_version,
                translated_lines=len(reading.translated_lines),
                unsafe_lines=len(reading.unsafe_lines),
            )
            for name, reading in sorted((languages or {}).items())
        ],
    )
    excluded = {"receipt_hash"} | (set() if receipt.languages else {"languages"})
    body = receipt.model_dump(mode="json", exclude=excluded)
    receipt.receipt_hash = _sha256(json.dumps(body, sort_keys=True, separators=(",", ":")))
    return receipt


# --- the plain model, side by side ---------------------------------------------------------------


class AnswerSide(JarvisModel):
    label: str
    answer: str
    check: NarrativeCheck | None = None
    tally: ReceiptAnswer = Field(default_factory=ReceiptAnswer)
    # Dates and figures stated that no line of any file contains.
    ungrounded: list[str] = Field(default_factory=list)
    # Findings with a resolved citation behind the answer; the plain model cites nothing checkable.
    cited_findings: int = 0
    latency_ms: int = 0


class Comparison(JarvisModel):
    run_id: str
    question: str
    model: str
    evidence_lines: int
    truncated: bool = False
    baseline_prompt_version: int = BASELINE_PROMPT_VERSION
    plain: AnswerSide
    jarvis: AnswerSide
    generated_at: datetime = Field(default_factory=utcnow)


def evidence_lines(texts: dict[str, str]) -> list[EvidenceText]:
    """Every non-blank line of every file, named by file and line: the pool both answers face."""
    pool: list[EvidenceText] = []
    for name, text in sorted(texts.items()):
        for number, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                pool.append(EvidenceText(source=f"{name}:{number}", content=line.strip()))
    return pool


def baseline_prompt(question: str, texts: dict[str, str]) -> tuple[str, bool]:
    parts: list[str] = []
    used = 0
    truncated = False
    for name, text in sorted(texts.items()):
        room = MAX_BASELINE_CHARS - used
        if room <= 0:
            truncated = True
            break
        body = text[:room]
        truncated = truncated or len(body) < len(text)
        used += len(body)
        parts.append(f"=== {name} ===\n{body}")
    return _BASELINE_PROMPT.format(documents="\n\n".join(parts), question=question), truncated


def answer_of(text: str) -> str:
    """The `answer` field of the reply, or the reply itself when it is not that JSON."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return text.strip()
    answer = parsed.get("answer") if isinstance(parsed, dict) else None
    return answer.strip() if isinstance(answer, str) else text.strip()


def score(
    label: str, answer: str, pool: list[EvidenceText], *, cited: int = 0, latency_ms: int = 0
) -> AnswerSide:
    check = check_narrative(SectionKind.EXECUTIVE_SUMMARY, answer, pool)
    ungrounded = (
        list(dict.fromkeys(v for s in check.sentences for v in s.ungrounded)) if check else []
    )
    return AnswerSide(
        label=label,
        answer=answer,
        check=check,
        tally=tally(check),
        ungrounded=ungrounded,
        cited_findings=cited,
        latency_ms=latency_ms,
    )


async def compare(
    provider: LLMProvider,
    *,
    run_id: str,
    question: str,
    texts: dict[str, str],
    findings: list[Finding],
    report: FinalReport | None,
    jarvis_latency_ms: int = 0,
) -> Comparison:
    prompt, truncated = baseline_prompt(question, texts)
    # JSON, as every engine role asks: without it a reasoning model (qwen3) writes its working
    # into the answer even with thinking off, and the comparison would score the working.
    response = await provider.complete(
        CompletionRequest(prompt=prompt, role="baseline", max_tokens=1024, json_mode=True)
    )
    pool = evidence_lines(texts)
    cited = sum(1 for f in findings if any(e.is_resolved for e in f.evidence))
    return Comparison(
        run_id=run_id,
        question=question,
        model=response.model or provider.model_id,
        evidence_lines=len(pool),
        truncated=truncated,
        plain=score("Plain model", answer_of(response.text), pool, latency_ms=response.latency_ms),
        jarvis=score(
            "JARVIS", summary_text(report), pool, cited=cited, latency_ms=jarvis_latency_ms
        ),
    )
