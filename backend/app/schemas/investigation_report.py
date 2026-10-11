"""The investigation report (Phase 51): one structured object, exported as JSON, PDF and DOCX.

Built from the run as it stands - findings with their statement types, confidence, reviews and
challenges; the evidence with its hashes, authority and integrity; the hypotheses, the plan, the
trace. Nothing in it is written by a model except the narrative carried from synthesis, which keeps
its sentence-by-sentence grounding verdicts. The executive summary and the risk come only from
findings that count: verified, and approved where review is required (Phase 50).

The report carries a SHA-256 of its own canonical content, so an exported copy can be checked
against the one the system produced.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.schemas.common import JarvisModel, utcnow


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_ORDER = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


class ReportFinding(JarvisModel):
    finding_id: str
    claim: str
    statement: str
    severity: Severity
    severity_reason: str
    confidence: float
    confidence_explained: str
    verification: str
    review: str
    challenge: str = ""
    citations: list[str] = Field(default_factory=list)
    # Currency or unit problems found by the deterministic check (UNIT_MISMATCH).
    unit_issues: list[str] = Field(default_factory=list)


class ReportEvidence(JarvisModel):
    document: str
    evidence_id: str = ""
    sha256: str = ""
    authority: str = ""
    integrity: str = ""
    cited_by: list[str] = Field(default_factory=list)


class TimelineEntry(JarvisModel):
    date: str
    event: str
    source: str


class ReportSectionText(JarvisModel):
    heading: str
    lines: list[str] = Field(default_factory=list)


class InvestigationReport(JarvisModel):
    report_id: str
    run_id: str
    case_id: str = ""
    objective: str
    generated_at: datetime = Field(default_factory=utcnow)
    model: str = ""
    # SHA-256 of the canonical JSON of the content: everything but this field and `generated_at`.
    content_hash: str = ""

    risk: Severity = Severity.INFO
    risk_reason: str = ""
    executive_summary: list[str] = Field(default_factory=list)

    established: list[ReportFinding] = Field(default_factory=list)
    awaiting_review: list[ReportFinding] = Field(default_factory=list)
    not_established: list[ReportFinding] = Field(default_factory=list)

    evidence: list[ReportEvidence] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    path: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    narrative: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)

    def sections(self) -> list[ReportSectionText]:
        """The report in reading order, as headed lists of lines - what every renderer draws."""

        def finding_line(f: ReportFinding) -> str:
            cites = ", ".join(f.citations) or "no resolved citation"
            extras = (f"; challenge: {f.challenge}" if f.challenge else "") + (
                f"; UNIT_MISMATCH: {'; '.join(f.unit_issues)}" if f.unit_issues else ""
            )
            return (
                f"[{f.finding_id}] {f.claim} ({f.statement}, {f.severity.value}: "
                f"{f.severity_reason}; confidence {f.confidence:.2f}; {f.verification}; "
                f"review {f.review}{extras}; {cites})"
            )

        return [
            ReportSectionText(
                heading="Risk",
                lines=[f"{self.risk.value}: {self.risk_reason}"],
            ),
            ReportSectionText(heading="Executive summary", lines=self.executive_summary),
            ReportSectionText(
                heading="Established findings",
                lines=[finding_line(f) for f in self.established] or ["None."],
            ),
            ReportSectionText(
                heading="Awaiting review",
                lines=[finding_line(f) for f in self.awaiting_review] or ["None."],
            ),
            ReportSectionText(
                heading="Not established",
                lines=[finding_line(f) for f in self.not_established] or ["None."],
            ),
            ReportSectionText(
                heading="Evidence",
                lines=[
                    f"{e.document}: {e.evidence_id or 'not in the locker'}, "
                    f"sha256 {e.sha256[:16] or '-'}, authority {e.authority or '-'}, "
                    f"integrity {e.integrity or '-'}"
                    + (f"; cited by {', '.join(e.cited_by)}" if e.cited_by else "")
                    for e in self.evidence
                ]
                or ["None."],
            ),
            ReportSectionText(
                heading="Timeline",
                lines=[f"{t.date} - {t.event} ({t.source})" for t in self.timeline] or ["None."],
            ),
            ReportSectionText(heading="Contradictions", lines=self.contradictions or ["None."]),
            ReportSectionText(heading="Competing explanations", lines=self.hypotheses or ["None."]),
            ReportSectionText(
                heading="Unknowns and next evidence", lines=self.unknowns or ["None."]
            ),
            ReportSectionText(heading="Recommendations", lines=self.recommendations or ["None."]),
            ReportSectionText(heading="Limitations", lines=self.limitations or ["None."]),
            ReportSectionText(heading="Investigation path", lines=self.path or ["None."]),
            ReportSectionText(
                heading="Narrative (model-written, checked)", lines=self.narrative or ["None."]
            ),
            ReportSectionText(
                heading="Trace",
                lines=[
                    f"{e.get('t', '')} {e.get('event', '')} {e.get('detail', '')}".strip()
                    for e in self.trace
                ]
                or ["None."],
            ),
        ]
