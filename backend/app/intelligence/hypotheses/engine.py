"""Competing explanations, tested against the findings (Phase 47).

Runs once the findings are final, and only when the objective asks for an explanation ("why did the
server go offline?"); a question that asks whether two documents agree has no use for one. Two model
calls at most:

1. **propose** two to four explanations, each with what would decide it and a search for it;
2. **test** which verified findings support or contradict each.

Everything after that is computed, not asked: an explanation's support is the confidence of the
verified findings for it, minus those against it. It is SUPPORTED only when that is high enough
*and* clearly ahead of the next; REJECTED when verified findings against it outweigh those for it;
otherwise OPEN. An open explanation gets its next best evidence: lines in the attached documents
that match its search (a SEARCH, with the lines as leads - not findings, nothing has checked them),
or, when nothing attached bears on it, a request for what a person must provide.

The leads do not re-enter the replanning loop. A lead becomes evidence through a new investigation
(the console offers one, prefilled), so this step can never change the run's findings.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from app.core.agent_config import load_yaml
from app.core.logging import get_logger
from app.llm.errors import LLMError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.evidence import EvidenceGap
from app.schemas.finding import Finding
from app.schemas.hypothesis import (
    FindingRelation,
    Hypothesis,
    HypothesisSet,
    HypothesisStatus,
    Lead,
    NextEvidence,
    NextEvidenceKind,
    Relation,
)
from app.tools.loader import source_ref

log = get_logger(__name__)

# An objective that asks for an explanation. Deliberately narrow: "determine whether the documents
# agree" is a comparison, and adding hypotheses to it would cost two calls and explain nothing.
_EXPLANATORY = re.compile(
    r"\b(why|cause[sd]?|caus(?:ing|ation)|explain\w*|reasons?\s+for|what\s+happened|"
    r"how\s+did|responsible\s+for|led\s+to|root\s+cause)\b",
    re.IGNORECASE,
)


def wants_explanation(objective: str) -> bool:
    return bool(_EXPLANATORY.search(objective))


class CandidateHypothesis(JarvisModel):
    statement: str = ""
    decisive_evidence: str = ""
    search_query: str = ""


class CandidateHypotheses(JarvisModel):
    hypotheses: list[CandidateHypothesis] = Field(default_factory=list)


class HypothesisVerdict(JarvisModel):
    hypothesis: int = 0
    finding_id: str = ""
    relation: str = "NEUTRAL"


class HypothesisVerdicts(JarvisModel):
    verdicts: list[HypothesisVerdict] = Field(default_factory=list)


class HypothesisSettings(JarvisModel):
    enabled: bool = True
    min: int = 2
    max: int = 4
    supported_min: float = 0.5
    supported_margin: float = 0.3
    rejected_min: float = 0.5
    max_leads: int = 3


def get_hypothesis_settings() -> HypothesisSettings:
    raw: Any = load_yaml("agent.yaml").get("hypotheses", {})
    return HypothesisSettings.model_validate(raw if isinstance(raw, dict) else {})


def _relation(raw: str) -> Relation:
    try:
        return Relation(raw.strip().upper())
    except ValueError:
        return Relation.NEUTRAL


def search_leads(
    query: str,
    documents: dict[str, str],
    page_starts: dict[str, list[int]],
    limit: int,
) -> list[Lead]:
    """Lines in the run's documents that match a query, best first - the document search tool's
    lexical rule, run directly: no model call, nothing to verify."""
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    if not terms:
        return []
    scored: list[tuple[float, str, int, str]] = []
    for name, text in documents.items():
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            hits = sum(1 for term in terms if term in lowered)
            # Half the terms at least: one common word matching is not a lead.
            if hits and hits / len(terms) >= 0.5:
                scored.append((hits / len(terms), name, number, line.strip()[:300]))
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    return [
        Lead(locator=source_ref(name, number, page_starts), text=text)
        for _, name, number, text in scored[:limit]
    ]


def rank(
    hypotheses: list[Hypothesis], settings: HypothesisSettings
) -> tuple[list[Hypothesis], bool, str]:
    """Statuses from computed support, ranked best first; whether the question is determined."""
    for h in hypotheses:
        h.support = round(sum(r.confidence for r in h.supporting), 3)
        h.against = round(sum(r.confidence for r in h.contradicting), 3)
        if h.against - h.support >= settings.rejected_min:
            h.status = HypothesisStatus.REJECTED
            h.status_reason = (
                f"verified findings against it ({h.against:.2f}) outweigh those for it "
                f"({h.support:.2f})"
            )
        else:
            h.status = HypothesisStatus.OPEN
    ordered = sorted(hypotheses, key=lambda h: h.net, reverse=True)
    live = [h for h in ordered if h.status is not HypothesisStatus.REJECTED]
    if live:
        best = live[0]
        runner_up = live[1].net if len(live) > 1 else 0.0
        margin = best.net - runner_up
        if best.net >= settings.supported_min and margin >= settings.supported_margin:
            best.status = HypothesisStatus.SUPPORTED
            best.status_reason = (
                f"net support {best.net:.2f}, {margin:.2f} ahead of the next explanation"
            )
    for h in live:
        if h.status is HypothesisStatus.OPEN:
            h.status_reason = (
                f"net support {h.net:.2f}: the verified findings do not separate it from the others"
            )
    supported = [h for h in ordered if h.status is HypothesisStatus.SUPPORTED]
    determined = len(supported) == 1
    if determined:
        summary = f"Supported: {supported[0].statement}"
    elif live:
        summary = (
            f"Undetermined: {len(live)} explanation(s) remain open; the findings do not decide "
            "between them."
        )
    else:
        summary = "Every proposed explanation is contradicted by the verified findings."
    return ordered, determined, summary


class HypothesisEngine:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def run(
        self,
        objective: str,
        findings: list[Finding],
        gaps: list[EvidenceGap],
        documents: dict[str, str],
        page_starts: dict[str, list[int]] | None = None,
        *,
        emit: object | None = None,
    ) -> HypothesisSet:
        settings = get_hypothesis_settings()
        result = HypothesisSet(question=objective)
        if not settings.enabled:
            result.skipped_reason = "hypotheses are switched off (agent.yaml: hypotheses.enabled)"
            return result
        if not wants_explanation(objective):
            result.skipped_reason = "the objective does not ask for an explanation"
            return result

        verified = [f for f in findings if f.is_verified]
        listed = (
            "\n".join(
                f"- {f.finding_id} ({'verified' if f.is_verified else 'not verified'}): {f.claim}"
                for f in findings
            )
            or "(none)"
        )
        missing = "\n".join(f"- {g.missing}" for g in gaps if not g.resolved) or "(none)"

        try:
            proposed = await generate_structured(
                self._provider,
                CandidateHypotheses,
                self._prompts.get("hypotheses").render(
                    objective=objective, findings=listed, gaps=missing
                ),
                role="hypotheses",
                emit=emit,
            )
        except LLMError as exc:
            log.warning("hypotheses_failed", error=str(exc))
            result.skipped_reason = "the model's proposals could not be read"
            result.llm_calls = 1
            return result
        result.llm_calls = 1

        candidates = [c for c in proposed.hypotheses if c.statement.strip()][: settings.max]
        if len(candidates) < settings.min:
            result.skipped_reason = (
                f"{len(candidates)} explanation(s) proposed; competing explanations need "
                f"{settings.min}"
            )
            return result

        hypotheses = [
            Hypothesis(
                hypothesis_id=f"H-{index}",
                statement=c.statement.strip(),
                decisive_evidence=c.decisive_evidence.strip(),
            )
            for index, c in enumerate(candidates, start=1)
        ]
        queries = {
            h.hypothesis_id: c.search_query.strip()
            for h, c in zip(hypotheses, candidates, strict=True)
        }

        if verified:
            numbered = "\n".join(f"{i}. {h.statement}" for i, h in enumerate(hypotheses, start=1))
            facts = "\n".join(f"- {f.finding_id}: {f.claim}" for f in verified)
            try:
                tested = await generate_structured(
                    self._provider,
                    HypothesisVerdicts,
                    self._prompts.get("hypothesis_test").render(
                        hypotheses=numbered, findings=facts
                    ),
                    role="hypotheses",
                    emit=emit,
                )
            except LLMError as exc:
                log.warning("hypothesis_test_failed", error=str(exc))
                tested = HypothesisVerdicts()
            result.llm_calls = 2
            by_id = {f.finding_id: f for f in verified}
            seen: set[tuple[int, str]] = set()
            for verdict in tested.verdicts:
                finding = by_id.get(verdict.finding_id.strip())
                key = (verdict.hypothesis, verdict.finding_id.strip())
                # Only real hypotheses and verified findings count, each pair once.
                if finding is None or not 1 <= verdict.hypothesis <= len(hypotheses) or key in seen:
                    continue
                seen.add(key)
                relation = _relation(verdict.relation)
                if relation is Relation.NEUTRAL:
                    continue
                entry = FindingRelation(
                    finding_id=finding.finding_id,
                    relation=relation,
                    confidence=finding.confidence.value,
                )
                target = hypotheses[verdict.hypothesis - 1]
                (
                    target.supporting if relation is Relation.SUPPORTS else target.contradicting
                ).append(entry)

        ordered, determined, summary = rank(hypotheses, settings)
        for h in ordered:
            if h.status is not HypothesisStatus.OPEN:
                continue
            query = queries.get(h.hypothesis_id) or h.decisive_evidence
            leads = search_leads(query, documents, page_starts or {}, settings.max_leads)
            if leads:
                h.next_evidence = NextEvidence(
                    kind=NextEvidenceKind.SEARCH,
                    text=f"Read these lines next: they match the evidence that would decide it "
                    f"({h.decisive_evidence or query}).",
                    query=query,
                    leads=leads,
                )
            else:
                h.next_evidence = NextEvidence(
                    kind=NextEvidenceKind.ANALYST_REQUEST,
                    text=f"Nothing attached bears on it. Needed: {h.decisive_evidence or query}.",
                    query=query,
                )
        result.hypotheses = ordered
        result.determined = determined
        result.summary = summary
        return result
