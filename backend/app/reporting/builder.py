"""Build the investigation report from a run as it stands (Phase 51).

Everything is read from what the run, the locker, the reviews and the challenges already hold; the
only model-written text is synthesis's narrative, carried with its grounding verdicts. The executive
summary is the claims of the findings that count (verified, and approved where review is required),
each with its citation - grounded by construction, since each sentence is a checked claim.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field

from app.core.agent_config import load_yaml
from app.core.config import get_settings
from app.evidence.authority import label as authority_label
from app.evidence.authority import tier_for_name
from app.intelligence.challenge import ChallengeOutcome, ChallengeResult
from app.intelligence.temporal import find_dates
from app.orchestration.labels import step_label
from app.orchestration.mission import MissionResult
from app.packs import Pack
from app.reporting.units import unit_mismatch
from app.review.service import counts_as_established
from app.schemas.common import JarvisModel
from app.schemas.event import ExecutionEvent
from app.schemas.evidence_locker import EvidenceItem
from app.schemas.finding import Finding, StatementType
from app.schemas.hypothesis import HypothesisStatus
from app.schemas.investigation_report import (
    SEVERITY_ORDER,
    InvestigationReport,
    ReportEvidence,
    ReportFinding,
    Severity,
    TimelineEntry,
)
from app.schemas.review import FindingReview, ReviewState


class ReportSettings(JarvisModel):
    # Findings of these severities are challenged before a report, when nobody has yet (Phase 48).
    challenge_before_report: list[Severity] = Field(
        default_factory=lambda: [Severity.HIGH, Severity.CRITICAL]
    )


def get_report_settings() -> ReportSettings:
    return _settings(str(get_settings().agent_dir))


@lru_cache
def _settings(agent_dir: str) -> ReportSettings:
    if not (Path(agent_dir) / "config" / "report.yaml").exists():
        return ReportSettings()
    raw = load_yaml("report.yaml")
    return ReportSettings.model_validate(
        {"challenge_before_report": raw.get("challenge_before_report", ["HIGH", "CRITICAL"])}
    )


class SeverityRules(JarvisModel):
    unit_mismatch: Severity = Severity.HIGH
    contradiction: Severity = Severity.HIGH
    overturned: Severity = Severity.HIGH
    risk: Severity = Severity.MEDIUM
    contested: Severity = Severity.MEDIUM
    default: Severity = Severity.LOW
    case_floor: dict[str, Severity] = Field(
        default_factory=lambda: {"CRITICAL": Severity.HIGH, "HIGH": Severity.MEDIUM}
    )


def get_severity_rules() -> SeverityRules:
    return _rules(str(get_settings().agent_dir))


@lru_cache
def _rules(agent_dir: str) -> SeverityRules:
    if not (Path(agent_dir) / "config" / "report.yaml").exists():
        return SeverityRules()
    raw = load_yaml("report.yaml").get("severity", {})
    return SeverityRules.model_validate(raw if isinstance(raw, dict) else {})


def _higher(a: Severity, b: Severity) -> Severity:
    return a if SEVERITY_ORDER.index(a) >= SEVERITY_ORDER.index(b) else b


def severity_of(
    finding: Finding,
    *,
    unit_issue: str,
    challenge: ChallengeResult | None,
    case_severity: str,
    rules: SeverityRules,
) -> tuple[Severity, str]:
    """The highest rule the finding matches, and the rule's words."""
    matched: list[tuple[Severity, str]] = [(rules.default, "no rule raised it")]
    if unit_issue:
        matched.append((rules.unit_mismatch, f"UNIT_MISMATCH: {unit_issue}"))
    if finding.statement_type is StatementType.CONTRADICTION:
        matched.append((rules.contradiction, "it reports a contradiction"))
    if finding.statement_type is StatementType.RISK:
        matched.append((rules.risk, "proposed as a risk"))
    if challenge is not None and challenge.outcome is ChallengeOutcome.OVERTURNED:
        matched.append((rules.overturned, "a challenge overturned it"))
    if challenge is not None and challenge.outcome is ChallengeOutcome.CONTESTED:
        matched.append((rules.contested, "a challenge contested it"))
    floor = rules.case_floor.get(case_severity)
    if floor is not None:
        matched.append((floor, f"its case is {case_severity}"))
    best = max(matched, key=lambda m: SEVERITY_ORDER.index(m[0]))
    return best


def content_hash(report: InvestigationReport) -> str:
    """SHA-256 of what the report says. Not of when it was generated: two builds of the same run in
    the same state - the page and a download of it - carry the same hash."""
    payload = report.model_dump(mode="json", exclude={"content_hash", "generated_at"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_report(
    result: MissionResult,
    *,
    case_id: str = "",
    case_severity: str = "",
    items: dict[str, EvidenceItem] | None = None,
    authority: dict[str, str] | None = None,
    reviews: dict[str, FindingReview] | None = None,
    challenges: dict[str, ChallengeResult] | None = None,
    events: list[ExecutionEvent] | None = None,
    model: str = "",
    receipt_hash: str = "",
    pack: Pack | None = None,
) -> InvestigationReport:
    rules = get_severity_rules()
    items = items or {}
    authority = authority or {}
    reviews = reviews or {}
    challenges = challenges or {}

    established: list[ReportFinding] = []
    awaiting: list[ReportFinding] = []
    not_established: list[ReportFinding] = []
    for finding in result.findings:
        cited = [ref.as_ref() for ref in finding.evidence if ref.is_resolved]
        issue = unit_mismatch(finding.claim, [result.evidence_text.get(c, "") for c in cited])
        challenge = challenges.get(finding.finding_id)
        review = reviews.get(finding.finding_id)
        severity, reason = severity_of(
            finding,
            unit_issue=issue,
            challenge=challenge,
            case_severity=case_severity,
            rules=rules,
        )
        # The organisation's domain pack can raise a severity, never lower one (v4 Phase 10).
        raised = pack.severity_for(finding.claim) if pack is not None else None
        if raised is not None and SEVERITY_ORDER.index(raised[0]) > SEVERITY_ORDER.index(severity):
            severity, reason = raised
        verdict = finding.verification.status.value if finding.verification else "UNVERIFIED"
        entry = ReportFinding(
            finding_id=finding.finding_id,
            claim=_shown_claim(finding, review),
            statement=finding.statement_type.value,
            severity=severity,
            severity_reason=reason,
            confidence=round(finding.confidence.value, 3),
            confidence_explained=finding.confidence.explain(),
            verification=verdict,
            review=_review_text(review),
            challenge=f"{challenge.outcome.value}: {challenge.summary}" if challenge else "",
            citations=cited,
            unit_issues=[issue] if issue else [],
            quotes={c: _quote(result.evidence_text.get(c, ""), c) for c in cited},
        )
        rejected_by_review = review is not None and review.state is ReviewState.REJECTED
        if counts_as_established(finding, review) and not issue and not rejected_by_review:
            established.append(entry)
        elif (
            finding.is_verified
            and review is not None
            and not review.settled
            and not rejected_by_review
        ):
            awaiting.append(entry)
        else:
            not_established.append(entry)

    risk = Severity.INFO
    risk_reason = "no established finding"
    for entry in established:
        if _higher(entry.severity, risk) is entry.severity and entry.severity is not risk:
            risk, risk_reason = entry.severity, f"{entry.finding_id}: {entry.severity_reason}"

    documents = sorted(
        {ref.locator.document_id for f in result.findings for ref in f.evidence if ref.is_resolved}
        | {d.name for d in result.objective.scope.documents}
    )
    evidence = [
        ReportEvidence(
            document=name,
            evidence_id=items[name].evidence_id if name in items else "",
            sha256=items[name].sha256 if name in items else "",
            authority=authority_label(authority.get(name) or tier_for_name(name)[0]),
            integrity=items[name].integrity.value if name in items else "",
            cited_by=sorted(
                {
                    f.finding_id
                    for f in result.findings
                    for ref in f.evidence
                    if ref.is_resolved and ref.locator.document_id == name
                }
            ),
        )
        for name in documents
    ]

    report = InvestigationReport(
        report_id=f"RPT-{result.run_id}",
        run_id=result.run_id,
        case_id=case_id,
        objective=result.objective.text,
        model=model,
        risk=risk,
        risk_reason=risk_reason,
        executive_summary=[
            f"{e.claim} [{e.finding_id}; {', '.join(e.citations)}]" for e in established
        ]
        or [
            "No finding is established: see what awaits review, what was not established, and the "
            "limitations."
        ],
        established=established,
        awaiting_review=awaiting,
        not_established=not_established,
        evidence=evidence,
        timeline=_timeline(result, established),
        path=_path(result),
        contradictions=_contradictions(result, reviews),
        hypotheses=_hypotheses(result),
        unknowns=_unknowns(result),
        recommendations=_recommendations(result, established, awaiting, reviews),
        limitations=[
            *(lim.description for lim in (result.report.limitations if result.report else [])),
            *([f"{len(awaiting)} finding(s) await a reviewer's decision"] if awaiting else []),
        ],
        narrative=_narrative(result),
        trace=_trace(events or []),
        receipt_hash=receipt_hash,
    )
    report.content_hash = content_hash(report)
    return report


def _quote(text: str, locator: str) -> str:
    """The cited line's text, without the locator some evidence text carries in front of it."""
    prefix = f"{locator}: "
    return (text[len(prefix) :] if text.startswith(prefix) else text).strip()[:400]


def _shown_claim(finding: Finding, review: FindingReview | None) -> str:
    if review is not None and review.state is ReviewState.MODIFIED and review.history:
        return review.history[-1].modified_claim or finding.claim
    return finding.claim


def _review_text(review: FindingReview | None) -> str:
    if review is None or (not review.required and not review.history):
        return "not required"
    if not review.history:
        return f"PENDING ({'; '.join(review.required_because)})"
    last = review.history[-1]
    return f"{last.state.value} by {last.reviewer}" + (f": {last.reason}" if last.reason else "")


def _timeline(result: MissionResult, established: list[ReportFinding]) -> list[TimelineEntry]:
    entries: dict[tuple[str, str], TimelineEntry] = {}
    knowledge = result.knowledge
    if knowledge is not None:
        names = {e.entity_id: e.name for e in knowledge.entities}
        for claim in knowledge.claims:
            if not claim.grounded:
                continue
            for _, date in find_dates(claim.value):
                subject = names.get(claim.entity_id, claim.entity_id)
                attribute = claim.attribute.replace("_", " ")
                event = f"{subject} {attribute}: {claim.value}"
                entries[(date.iso(), event)] = TimelineEntry(
                    date=date.iso(), event=event, source=claim.source
                )
    for finding in established:
        for _, date in find_dates(finding.claim):
            entries[(date.iso(), finding.claim)] = TimelineEntry(
                date=date.iso(),
                event=f"{finding.finding_id}: {finding.claim}",
                source=", ".join(finding.citations),
            )
    return sorted(entries.values(), key=lambda e: (e.date, e.event))


def _path(result: MissionResult) -> list[str]:
    if result.plan is None:
        return []
    return [
        f"{t.task_id} {step_label(t.task_type, t.status)} - why: {t.rationale or 'not recorded'}"
        + (f" (added in revision {t.created_by_revision})" if t.created_by_revision else "")
        for t in result.plan.tasks
    ]


def _contradictions(result: MissionResult, reviews: dict[str, FindingReview]) -> list[str]:
    lines = [
        f"[{f.finding_id}] {f.claim} - review {_review_text(reviews.get(f.finding_id))}"
        for f in result.findings
        if f.statement_type is StatementType.CONTRADICTION
    ]
    if result.knowledge is not None:
        for conflict in result.knowledge.conflicts:
            sides = "; ".join(
                f"{s.sources[0] if s.sources else '?'} gives {s.value}" for s in conflict.sides
            )
            lines.append(
                f"knowledge graph: {conflict.entity_name} "
                f"{conflict.attribute.replace('_', ' ')} - {sides}"
            )
    return lines


def _hypotheses(result: MissionResult) -> list[str]:
    hs = result.hypotheses
    if hs is None or not hs.hypotheses:
        return [f"Not run: {hs.skipped_reason}"] if hs and hs.skipped_reason else []
    lines = [hs.summary]
    for h in hs.hypotheses:
        lines.append(
            f"{h.hypothesis_id} {h.status.value} (net {h.net:+.2f}): {h.statement}"
            + (f" - would decide it: {h.decisive_evidence}" if h.decisive_evidence else "")
        )
    return lines


def _unknowns(result: MissionResult) -> list[str]:
    lines = [f"Missing: {g.missing}" for g in result.gaps if not g.resolved]
    hs = result.hypotheses
    if hs is not None:
        for h in hs.hypotheses:
            if h.status is HypothesisStatus.OPEN and h.next_evidence is not None:
                leads = ", ".join(lead.locator for lead in h.next_evidence.leads)
                lines.append(
                    f"{h.hypothesis_id} next: {h.next_evidence.text}"
                    + (f" ({leads})" if leads else "")
                )
    return lines


def _recommendations(
    result: MissionResult,
    established: list[ReportFinding],
    awaiting: list[ReportFinding],
    reviews: dict[str, FindingReview],
) -> list[str]:
    lines = [f"Decide on {f.finding_id}: {f.review}" for f in awaiting]
    for f in result.findings:
        if f.statement_type is StatementType.CONTRADICTION:
            cites = " vs ".join(ref.as_ref() for ref in f.evidence if ref.is_resolved)
            lines.append(f"Establish which source is current for {f.finding_id} ({cites})")
        if f.statement_type is StatementType.RECOMMENDATION and f.is_verified:
            lines.append(
                f"{f.finding_id} (proposed by the model, on {f.statement_basis.value}): {f.claim}"
            )
    for e in established:
        if e.unit_issues:
            lines.append(f"Confirm the currency of {e.finding_id}")
    hs = result.hypotheses
    if hs is not None:
        for h in hs.open:
            if h.decisive_evidence:
                lines.append(f"Obtain {h.decisive_evidence} to decide {h.hypothesis_id}")
    return lines


def _narrative(result: MissionResult) -> list[str]:
    report = result.report
    if report is None:
        return []
    verdicts = {c.section: c.overall.value for c in report.narrative_checks}
    return [
        f"{section.heading}: {section.narrative} "
        f"(grounding: {verdicts.get(section.kind, 'not checked')})"
        for section in report.sections
        if section.narrative
    ]


def _trace(events: list[ExecutionEvent]) -> list[dict[str, Any]]:
    return [
        {
            "t": e.offset_display,
            "event": e.event_type.value,
            "detail": (e.task_id or e.finding_id or ""),
        }
        for e in events
    ]
