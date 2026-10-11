"""Challenge JARVIS: a counter-analysis of one finding, on demand (Phase 48).

A finding is challenged by looking for what would make it wrong, not by asking a model whether it is
right:

1. **Counter-evidence** - every line in the run's documents, other than the ones the finding cites,
   that is about the same thing (at least half the claim's content words) and disagrees with it: a
   date or figure the claim's cannot be, or a negation ("cancelled", "not") the claim lacks.
2. **Its own lines** - whether the dates and figures the claim states are on the lines it cites
   (the temporal-consistency factor of Phase 46). A claim its own citation does not hold is
   contested by itself.
3. **The negated claim, verified** - when a verifier is given (the API passes the configured one),
   the claim is checked against the counter lines alone. A verdict that they support it dismisses
   them; CONTRADICTED or UNSUPPORTED confirms them.
4. **Authority** - counter-evidence from a strictly more authoritative source (Phase 45 tiers) can
   overturn a finding; from an equal or weaker one it contests it. Authority decides nothing about
   which side is true - it decides how much a challenge is allowed to move the number.
5. **Confidence, recomputed** - CONTESTED takes the disputed penalty, OVERTURNED the CONTRADICTED
   verdict cap (Phase 46). Before and after are both kept. The stored finding is not changed: a
   challenge is a second opinion beside it, recorded with who asked for it.

What it cannot catch, measured by the benchmark: a wrong *name* (a vendor, a person) with no date,
figure or negation to disagree on.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.evidence.authority import get_authority_config, tier_for_name
from app.evidence.authority import label as authority_label
from app.intelligence.confidence import assess
from app.intelligence.temporal import find_dates, find_figures
from app.schemas.common import JarvisModel, SourceLocator, utcnow
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Confidence, Finding
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from app.tools.loader import source_ref


class ChallengeOutcome(StrEnum):
    # Nothing in the documents disagrees with it.
    WITHSTOOD = "WITHSTOOD"
    # Something disagrees, from a source no stronger than its own, or its own line does not hold it.
    CONTESTED = "CONTESTED"
    # A strictly more authoritative source disagrees, and no verifier dismissed it.
    OVERTURNED = "OVERTURNED"


class CounterEvidence(JarvisModel):
    locator: str
    text: str
    reason: str
    authority: str
    # Strictly more authoritative than every document the finding cites.
    stronger: bool = False


class ChallengeResult(JarvisModel):
    finding_id: str
    claim: str
    outcome: ChallengeOutcome
    summary: str
    counter_evidence: list[CounterEvidence] = Field(default_factory=list)
    own_lines: str = ""
    negation_check: str = "not run: no verifier was given"
    authority_note: str = ""
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    after: Confidence = Field(default_factory=Confidence.none)
    challenged_by: str = "system"
    challenged_at: datetime = Field(default_factory=utcnow)


Verifier = Callable[[VerificationRequest], Awaitable[VerificationResult]]

_WORD = re.compile(r"[a-z][a-z0-9-]{2,}")
_STOP = frozenset(
    "the and for with that this from was were are has have had its their which who whom what when "
    "where will would shall should could been being not but all any per into onto over under than "
    "then there here also each both such only very more most less least does did done".split()
)
_NEGATION = re.compile(
    r"\b(not|never|no longer|cancel+ed|withdrawn|rejected|postponed|suspended|terminated|"
    r"abandoned|stopped)\b",
    re.IGNORECASE,
)
_MONTHS = frozenset(
    "january february march april may june july august september october november december".split()
)


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and w not in _MONTHS}


def _subject_overlap(claim: str, line: str) -> float:
    words = content_words(claim)
    if not words:
        return 0.0
    return len(words & content_words(line)) / len(words)


def disagreement(claim: str, line: str) -> str:
    """Why `line` disagrees with `claim`, or "" - dates, figures, or a negation the claim lacks."""
    claim_dates = [d for _, d in find_dates(claim)]
    line_dates = [d for _, d in find_dates(line)]
    if (
        claim_dates
        and line_dates
        and not any(a.compatible(b) for a in claim_dates for b in line_dates)
    ):
        return (
            f"gives {', '.join(line[s:e] for (s, e), _ in find_dates(line))} where the claim gives "
            f"{', '.join(claim[s:e] for (s, e), _ in find_dates(claim))}"
        )
    claim_figures = {v for _, v in find_figures(claim)}
    line_figures = {v for _, v in find_figures(line)}
    if claim_figures and line_figures and not claim_figures & line_figures:
        return (
            f"gives {', '.join(w for w, _ in find_figures(line))} where the claim gives "
            f"{', '.join(w for w, _ in find_figures(claim))}"
        )
    negation = _NEGATION.search(line)
    if negation and not _NEGATION.search(claim):
        return f'says "{negation.group(0)}" where the claim does not'
    return ""


def _weight(document: str, authority: dict[str, str] | None) -> tuple[float, str]:
    tier_id = (authority or {}).get(document) or tier_for_name(document)[0]
    tier = get_authority_config().tier(tier_id)
    return (tier.weight if tier else 0.75), tier_id


def find_counter_evidence(
    finding: Finding,
    documents: dict[str, str],
    page_starts: dict[str, list[int]] | None = None,
    authority: dict[str, str] | None = None,
    *,
    min_overlap: float = 0.5,
) -> list[CounterEvidence]:
    cited_rows = {
        (ref.locator.document_id, ref.locator.row)
        for ref in finding.evidence
        if ref.is_resolved and ref.locator.row is not None
    }
    cited_documents = {ref.locator.document_id for ref in finding.evidence if ref.is_resolved}
    strongest_cited = max((_weight(d, authority)[0] for d in cited_documents), default=0.0)
    found: list[CounterEvidence] = []
    for name, text in documents.items():
        for number, line in enumerate(text.splitlines(), start=1):
            locator = source_ref(name, number, page_starts or {})
            if (name, number) in cited_rows:
                continue
            if _subject_overlap(finding.claim, line) < min_overlap:
                continue
            reason = disagreement(finding.claim, line)
            if not reason:
                continue
            weight, tier = _weight(name, authority)
            found.append(
                CounterEvidence(
                    locator=locator,
                    text=line.strip()[:300],
                    reason=reason,
                    authority=authority_label(tier),
                    stronger=weight > strongest_cited,
                )
            )
    return found


async def challenge(
    finding: Finding,
    documents: dict[str, str],
    *,
    page_starts: dict[str, list[int]] | None = None,
    authority: dict[str, str] | None = None,
    evidence_text: dict[str, str] | None = None,
    verifier: Verifier | None = None,
    actor: str = "system",
) -> ChallengeResult:
    before = finding.confidence.value
    counter = find_counter_evidence(finding, documents, page_starts, authority)

    own = assess(finding, authority=authority, evidence_text=evidence_text)
    temporal = next((f for f in own.factors if f.name == "temporal_consistency"), None)
    own_ok = temporal is None or not temporal.assessed or temporal.value >= 1.0
    own_lines = temporal.reason if temporal is not None else "nothing to check"

    negation = "not run: no counter-evidence to check against"
    dismissed = False
    if counter and verifier is not None:
        refs = [
            EvidenceRef(
                evidence_id=f"E-{i:03d}",
                locator=SourceLocator(document_id=c.locator.rsplit(":", 1)[0]),
                resolution=ResolutionStatus.RESOLVED,
            )
            for i, c in enumerate(counter, start=1)
        ]
        verdict = await verifier(
            VerificationRequest(
                claim=finding.claim,
                evidence=refs,
                evidence_content={c.locator: c.text for c in counter},
            )
        )
        negation = (
            f"checked against the counter lines alone: {verdict.status.value} ({verdict.verifier})"
        )
        dismissed = verdict.status is VerificationStatus.SUPPORTED
    elif counter:
        negation = "not run: no verifier was given (the deterministic rule alone)"

    stronger = [c for c in counter if c.stronger]
    if dismissed or (not counter and own_ok):
        outcome = ChallengeOutcome.WITHSTOOD
    elif stronger:
        outcome = ChallengeOutcome.OVERTURNED
    else:
        outcome = ChallengeOutcome.CONTESTED

    authority_note = (
        f"{len(stronger)} of {len(counter)} counter line(s) come from a more authoritative source"
        if counter
        else "no counter-evidence to weigh"
    )

    if outcome is ChallengeOutcome.WITHSTOOD:
        after = finding.confidence
    elif outcome is ChallengeOutcome.OVERTURNED:
        overturned = finding.model_copy(
            update={
                "verification": VerificationResult(
                    status=VerificationStatus.CONTRADICTED,
                    confidence=1.0,
                    verifier="challenge",
                    issues=[
                        VerificationIssue(
                            issue_type=IssueType.SOURCE_CONFLICT,
                            description=f"{stronger[0].locator} {stronger[0].reason}",
                        )
                    ],
                )
            }
        )
        after = assess(overturned, authority=authority, evidence_text=evidence_text)
    else:
        disputed = [c.locator for c in counter] or ["its own cited line"]
        after = assess(
            finding, authority=authority, evidence_text=evidence_text, disputed_by=disputed[:3]
        )

    if outcome is ChallengeOutcome.WITHSTOOD:
        summary = (
            "Withstood: nothing in the documents disagrees with it."
            if not counter
            else "Withstood: the verifier found the counter lines consistent with it."
        )
    elif outcome is ChallengeOutcome.OVERTURNED:
        summary = (
            f"Overturned: {stronger[0].locator} ({stronger[0].authority}) {stronger[0].reason}."
        )
    elif counter:
        summary = f"Contested: {counter[0].locator} ({counter[0].authority}) {counter[0].reason}."
    else:
        summary = f"Contested by its own citation: {own_lines}."

    return ChallengeResult(
        finding_id=finding.finding_id,
        claim=finding.claim,
        outcome=outcome,
        summary=summary,
        counter_evidence=counter,
        own_lines=own_lines,
        negation_check=negation if counter else "not run: no counter-evidence to check against",
        authority_note=authority_note,
        confidence_before=before,
        confidence_after=after.value,
        after=after,
        challenged_by=actor,
    )
