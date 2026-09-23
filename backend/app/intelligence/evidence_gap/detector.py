"""Evidence gap detection — the headline feature.

The interesting behaviour is not "I'm not sure". It is *"I am missing the approved baseline
completion date, and retrieving it would resolve this claim."* The difference is that the
second one is **actionable**: a named element can be turned into a retrieval query, and a
retrieval query can be turned into a task.

What makes that possible is **claim decomposition**. A claim is split into its verifiable
elements — dates, amounts, entities, relations — and support is checked *per element*
against the text of the evidence that actually resolved. Checking a claim as a whole can only
ever produce "supported" or "not supported". Checking its elements tells you *which part* is
unsupported, and that is the thing you can go and fix.

Detection is deterministic. The model is not asked whether a gap exists, and the answer does
not vary between runs on the same evidence. That is what makes `EVIDENCE_GAP_DETECTED` a
measurable event rather than a mood.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.schemas.common import gap_id, task_id
from app.schemas.event import EventType
from app.schemas.evidence import ClaimElement, Evidence, EvidenceGap, GapType
from app.schemas.finding import Finding
from app.schemas.task import Task, TaskType

log = get_logger(__name__)

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_AMOUNT = re.compile(r"\b\d[\d,]{2,}(?:\.\d{2})?\b")
_ENTITY = re.compile(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+)*\b")

# Words that signal a claim is measured against something that must itself be established.
# "The project slipped against the approved baseline" is only as good as the baseline.
_BASELINE_TERMS = (
    "baseline",
    "approved",
    "planned",
    "original",
    "agreed",
    "authorised",
    "authorized",
    "sign-off",
    "signed off",
)

# Ordinary words that the entity pattern picks up at the start of a sentence.
_STOPWORDS = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "There",
        "It",
        "A",
        "An",
        "Project",
        "Report",
        "Total",
        "Spend",
        "Budget",
        "Date",
        "Actual",
        "Finance",
        "Delivery",
        "However",
        "According",
        "Based",
        "While",
    }
)


def decompose(claim: str) -> list[ClaimElement]:
    """Split a claim into the parts that can independently be checked.

    Deliberately conservative: it extracts what can be recognised structurally rather than
    guessing at semantics. A missed element produces a coarser gap, which is a smaller error
    than a fabricated one.
    """
    elements: list[ClaimElement] = []
    seen: set[str] = set()

    def add(text: str, kind: str) -> None:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            elements.append(ClaimElement(text=text.strip(), kind=kind))

    for match in _DATE.findall(claim):
        add(match, "date")
    for match in _AMOUNT.findall(claim):
        add(match, "quantity")
    for match in _ENTITY.findall(claim):
        if match.split()[0] not in _STOPWORDS:
            add(match, "entity")

    # The claim as a whole is always an element: a relation between the parts above is what
    # the claim actually asserts, and it can be unsupported even when every part is present.
    add(claim, "relation")
    return elements


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def check_support(elements: list[ClaimElement], evidence: list[Evidence]) -> list[ClaimElement]:
    """Mark each element supported when the evidence text contains it.

    Literal containment, not similarity. An element the evidence does not literally contain
    is reported as a gap, which at worst produces an unnecessary retrieval task - far
    cheaper than declaring a claim supported because two strings looked alike.
    """
    corpus = " ".join(e.content for e in evidence)
    haystack = _normalise(corpus)

    checked: list[ClaimElement] = []
    for element in elements:
        if element.kind == "relation":
            # A relation is supported when two or more distinct sources back the claim's
            # parts; a single source stating something is not the same as corroboration.
            supported = len({e.locator.document_id for e in evidence}) >= 2
        else:
            supported = _normalise(element.text) in haystack

        checked.append(
            element.model_copy(
                update={
                    "supported": supported,
                    "supporting_refs": [e.to_ref() for e in evidence] if supported else [],
                }
            )
        )
    return checked


def mentions_baseline(claim: str) -> bool:
    lowered = claim.lower()
    return any(term in lowered for term in _BASELINE_TERMS)


class EvidenceGapDetector:
    """Finds what is missing, names it, and proposes how to get it."""

    def __init__(self, *, start_index: int = 0) -> None:
        self._counter = start_index

    def detect(self, finding: Finding, evidence: list[Evidence]) -> list[EvidenceGap]:
        """Identify every specific missing piece of support for a finding."""
        gaps: list[EvidenceGap] = []
        relevant = [
            e
            for e in evidence
            if any(
                r.is_resolved and r.locator.as_ref() == e.locator.as_ref() for r in finding.evidence
            )
        ]

        # 1. Citations the binder could not resolve.
        for ref in finding.evidence:
            if ref.is_resolved:
                continue
            gaps.append(
                self._gap(
                    finding,
                    GapType.UNRESOLVED_CITATION,
                    missing=f"a source matching the citation '{ref.as_ref()}'",
                    severity=0.7,
                    query=f"{finding.claim[:120]}",
                    scope=[ref.locator.document_id] if ref.locator.document_id else [],
                )
            )

        elements = check_support(decompose(finding.claim), relevant)
        finding.elements = elements

        # 2. Claim elements nothing supports.
        for element in elements:
            if element.supported or element.kind == "relation":
                continue
            gaps.append(
                self._gap(
                    finding,
                    GapType.MISSING_SOURCE,
                    missing=f"a source stating {element.kind} '{element.text}'",
                    severity=0.6,
                    query=element.text,
                )
            )

        # 3. A comparison against a baseline nobody established.
        if mentions_baseline(finding.claim) and not self._baseline_in(relevant):
            gaps.append(
                self._gap(
                    finding,
                    GapType.MISSING_BASELINE,
                    missing="the approved baseline this claim is measured against",
                    severity=0.9,
                    query="approved baseline schedule original plan sign-off",
                )
            )

        # 4. Nothing resolved at all.
        if not relevant and not gaps:
            gaps.append(
                self._gap(
                    finding,
                    GapType.MISSING_SOURCE,
                    missing="any source supporting this claim",
                    severity=1.0,
                    query=finding.claim[:120],
                )
            )

        return gaps

    @staticmethod
    def _baseline_in(evidence: list[Evidence]) -> bool:
        corpus = " ".join(e.content for e in evidence).lower()
        return any(term in corpus for term in _BASELINE_TERMS)

    def _gap(
        self,
        finding: Finding,
        gap_type: GapType,
        *,
        missing: str,
        severity: float,
        query: str,
        scope: list[str] | None = None,
    ) -> EvidenceGap:
        self._counter += 1
        return EvidenceGap(
            gap_id=gap_id(self._counter),
            finding_id=finding.finding_id,
            gap_type=gap_type,
            missing=missing,
            severity=severity,
            suggested_query=query.strip(),
            suggested_scope=scope or [],
        )


def propose_task(gap: EvidenceGap, *, index: int) -> Task:
    """Turn a gap into an executable task.

    This is the step that makes gap detection more than a diagnostic. The task carries a
    concrete query derived from the named missing element, and records the gap that caused
    it, so an inserted task can always be explained.
    """
    return Task(
        task_id=task_id(index),
        task_type=TaskType.RETRIEVE_EVIDENCE,
        description=f"Retrieve {gap.missing}",
        inputs={"query": gap.suggested_query, "scope": gap.suggested_scope},
        created_for_gap_id=gap.gap_id,
    )


async def emit_gaps(gaps: list[EvidenceGap], emit: object | None) -> None:
    if emit is None:
        return
    emitter = getattr(emit, "emit", None)
    if emitter is None:
        return
    for gap in gaps:
        await emitter(
            EventType.EVIDENCE_GAP_DETECTED,
            payload={
                "type": gap.gap_type.value,
                "missing": gap.missing,
                "severity": gap.severity,
                "query": gap.suggested_query,
            },
            finding_id=gap.finding_id,
        )
