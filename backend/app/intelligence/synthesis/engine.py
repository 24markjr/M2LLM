"""Synthesis — assembling the report a human actually reads.

The governing rule: **facts are injected, prose is generated.** The model writes connective
narrative for two sections and nothing else. Every number, date, confidence and evidence
reference is placed by this module from state that is already settled.

That split matters because a report reads as authoritative. A model asked to "summarise the
findings" will happily round a figure, merge two dates, or promote a hypothesis to a
conclusion, and the result looks exactly as trustworthy as one that did not. Here it cannot:
there is nowhere for a generated number to enter.

The consequence worth stating plainly is that a report regenerates identically from stored
state, apart from the two narrative paragraphs.

**Rejected findings appear in the report.** Showing only what survived would make this a
highlight reel rather than an audit, and the temptation to drop them is exactly why the
section is mandatory.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.event import EventType
from app.schemas.evidence import EvidenceGap
from app.schemas.execution import Observation, TerminationReason
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.result import (
    ExecutionSummary,
    FinalReport,
    Limitation,
    ReportSection,
    SectionKind,
)

log = get_logger(__name__)


class ReportNarrative(JarvisModel):
    """The only two pieces of text the model contributes."""

    executive_summary: str = ""
    reasoning: str = ""


class SynthesisEngine:
    """Builds a `FinalReport` from settled state."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def synthesize(
        self,
        *,
        run_id: str,
        objective: Objective,
        findings: list[Finding],
        gaps: list[EvidenceGap],
        observations: list[Observation],
        execution: ExecutionSummary,
        termination: TerminationReason | None = None,
        emit: object | None = None,
    ) -> FinalReport:
        await self._event(emit, EventType.SYNTHESIS_STARTED, {"findings": len(findings)})

        verified = [f for f in findings if f.is_verified]
        rejected = [f for f in findings if f.is_rejected]
        uncertain = [f for f in findings if not f.is_verified and not f.is_rejected]
        unresolved = [g for g in gaps if not g.resolved]

        narrative = await self._write_narrative(
            objective, verified, uncertain, rejected, unresolved, execution
        )

        report = FinalReport(
            run_id=run_id,
            objective=objective.text,
            verified_findings=verified,
            uncertain_findings=uncertain,
            rejected_findings=rejected,
            unresolved_gaps=unresolved,
            execution=execution,
            limitations=self._limitations(
                findings, unresolved, observations, execution, termination
            ),
            overall_confidence=self._overall_confidence(verified),
            sections=self._sections(
                objective, verified, uncertain, rejected, unresolved, execution, narrative
            ),
        )

        await self._event(
            emit,
            EventType.SYNTHESIS_COMPLETED,
            {
                "verified": len(verified),
                "uncertain": len(uncertain),
                "rejected": len(rejected),
                "limitations": len(report.limitations),
            },
        )
        return report

    # --- narrative -------------------------------------------------------------

    async def _write_narrative(
        self,
        objective: Objective,
        verified: list[Finding],
        uncertain: list[Finding],
        rejected: list[Finding],
        gaps: list[EvidenceGap],
        execution: ExecutionSummary,
    ) -> ReportNarrative:
        prompt = self._prompts.get("synthesis").render(
            objective=objective.text,
            verified=_claims(verified) or "(none)",
            uncertain=_claims(uncertain) or "(none)",
            rejected=_claims(rejected) or "(none)",
            gaps="\n".join(f"- {g.missing}" for g in gaps) or "(none)",
            execution=(
                f"{execution.tasks_completed}/{execution.tasks_planned} tasks completed, "
                f"{execution.replan_iterations} replan iteration(s), "
                f"{execution.gaps_resolved}/{execution.gaps_detected} gaps closed"
            ),
        )
        try:
            return await generate_structured(
                self._provider, ReportNarrative, prompt, role="synthesis"
            )
        except StructuredOutputError:
            # A report without its narrative is still a complete, accurate report. Every
            # finding, number and citation is placed by this module regardless.
            log.warning("synthesis_narrative_failed")
            return ReportNarrative()

    # --- sections --------------------------------------------------------------

    def _sections(
        self,
        objective: Objective,
        verified: list[Finding],
        uncertain: list[Finding],
        rejected: list[Finding],
        gaps: list[EvidenceGap],
        execution: ExecutionSummary,
        narrative: ReportNarrative,
    ) -> list[ReportSection]:
        """All eleven sections, in presentation order. None is optional."""
        return [
            ReportSection(
                kind=SectionKind.EXECUTIVE_SUMMARY,
                heading="Executive Summary",
                narrative=narrative.executive_summary.strip()
                or self._fallback_summary(verified, uncertain, gaps),
            ),
            ReportSection(
                kind=SectionKind.INVESTIGATION_SCOPE,
                heading="Investigation Scope",
                items=[f"Objective: {objective.text}"]
                + [f"Document: {d.name}" for d in objective.scope.documents],
            ),
            ReportSection(
                kind=SectionKind.EXECUTION_SUMMARY,
                heading="Execution Summary",
                items=[
                    f"Tasks planned: {execution.tasks_planned}",
                    f"Tasks completed: {execution.tasks_completed}",
                    f"Tasks failed: {execution.tasks_failed}",
                    f"Tasks skipped: {execution.tasks_skipped}",
                    f"Tool calls: {execution.tool_calls}",
                    f"Documents processed: {execution.documents_processed}",
                    f"Replan iterations: {execution.replan_iterations}",
                    f"Evidence gaps: {execution.gaps_resolved} of {execution.gaps_detected} closed",
                ],
            ),
            ReportSection(
                kind=SectionKind.VERIFIED_FINDINGS,
                heading="Verified Findings",
                items=[_finding_line(f) for f in verified] or ["None."],
                finding_ids=[f.finding_id for f in verified],
            ),
            ReportSection(
                kind=SectionKind.EVIDENCE,
                heading="Evidence",
                items=_evidence_lines(verified + uncertain) or ["None."],
            ),
            ReportSection(
                kind=SectionKind.UNCERTAIN_FINDINGS,
                heading="Uncertain Findings",
                items=[_finding_line(f) for f in uncertain] or ["None."],
                finding_ids=[f.finding_id for f in uncertain],
            ),
            # Mandatory. A report showing only what survived is a highlight reel.
            ReportSection(
                kind=SectionKind.REJECTED_FINDINGS,
                heading="Rejected Findings",
                items=[_rejected_line(f) for f in rejected] or ["None."],
                finding_ids=[f.finding_id for f in rejected],
            ),
            ReportSection(
                kind=SectionKind.REASONING,
                heading="Reasoning",
                narrative=narrative.reasoning.strip()
                or "No connective reasoning was established between the findings.",
            ),
            ReportSection(
                kind=SectionKind.ACTIONS_PERFORMED,
                heading="Actions Performed",
                items=[
                    f"{execution.tasks_completed} task(s) executed across "
                    f"{execution.documents_processed} document(s)",
                    f"{execution.tool_calls} tool call(s)",
                    f"{execution.replan_iterations} adaptive replan iteration(s)",
                ],
            ),
            ReportSection(
                kind=SectionKind.CONFIDENCE,
                heading="Confidence",
                items=[_confidence_line(f) for f in verified + uncertain] or ["None."],
            ),
            ReportSection(
                kind=SectionKind.LIMITATIONS,
                heading="Limitations",
                items=["(generated from run facts - see the limitations list)"],
            ),
        ]

    # --- limitations -----------------------------------------------------------

    @staticmethod
    def _limitations(
        findings: list[Finding],
        gaps: list[EvidenceGap],
        observations: list[Observation],
        execution: ExecutionSummary,
        termination: TerminationReason | None,
    ) -> list[Limitation]:
        """Derived from what the run actually did, never from the model's modesty.

        A limitations section written by a model is a paragraph of hedging. One derived
        from skipped tasks, unresolved gaps and degraded verification tells a reader
        precisely how far to trust the rest of the document.
        """
        limitations: list[Limitation] = []

        if execution.tasks_skipped:
            limitations.append(
                Limitation(
                    description=(
                        f"{execution.tasks_skipped} planned task(s) could not be executed"
                    ),
                    cause="no registered tool served the required capability",
                )
            )

        if execution.tasks_failed:
            limitations.append(
                Limitation(
                    description=f"{execution.tasks_failed} task(s) failed",
                    cause="tool failure after retries and fallback were exhausted",
                )
            )

        for gap in gaps:
            limitations.append(
                Limitation(
                    description=f"Missing evidence: {gap.missing}",
                    cause=f"{gap.gap_type.value.lower().replace('_', ' ')}, not obtained",
                )
            )

        if any(o.compacted for o in observations):
            limitations.append(
                Limitation(
                    description="Some observations were summarised before reasoning",
                    cause="the accumulated context exceeded the model's token budget",
                )
            )

        degraded = [f for f in findings if f.verification is not None and f.verification.degraded]
        if degraded:
            limitations.append(
                Limitation(
                    description=(
                        f"{len(degraded)} finding(s) were verified by the fallback verifier"
                    ),
                    cause="the primary verification service was unavailable",
                )
            )

        if termination is TerminationReason.MAX_ITERATIONS:
            limitations.append(
                Limitation(
                    description="The investigation stopped at its iteration ceiling",
                    cause="unresolved findings remained when the replan budget ran out",
                )
            )
        elif termination is TerminationReason.BUDGET_EXHAUSTED:
            limitations.append(
                Limitation(
                    description="The investigation stopped when its budget ran out",
                    cause="the tool-call or wall-clock ceiling was reached",
                )
            )

        unsupported = [f for f in findings if not f.has_resolved_evidence]
        if unsupported:
            limitations.append(
                Limitation(
                    description=(
                        f"{len(unsupported)} claim(s) could not be tied to any source and "
                        "are reported as unverified"
                    ),
                    cause="cited locations did not resolve against retrieved content",
                )
            )

        return limitations

    @staticmethod
    def _overall_confidence(verified: list[Finding]) -> float:
        """Mean over verified findings only.

        Averaging in the uncertain ones would let a pile of unsupported claims drag down -
        or prop up - a number that is supposed to describe what was actually established.
        """
        if not verified:
            return 0.0
        return sum(f.confidence.value for f in verified) / len(verified)

    @staticmethod
    def _fallback_summary(
        verified: list[Finding], uncertain: list[Finding], gaps: list[EvidenceGap]
    ) -> str:
        parts = [
            f"The investigation established {len(verified)} verified finding(s)",
            f"and left {len(uncertain)} uncertain.",
        ]
        if gaps:
            parts.append(f"{len(gaps)} evidence gap(s) remain unresolved.")
        return " ".join(parts)

    @staticmethod
    async def _event(
        emit: object | None, event_type: EventType, payload: dict[str, object]
    ) -> None:
        if emit is None:
            return
        emitter = getattr(emit, "emit", None)
        if emitter is None:
            return
        await emitter(event_type, payload=payload)


# --- line builders: every figure comes from the finding, never from prose ------


def _claims(findings: list[Finding]) -> str:
    return "\n".join(f"- {f.claim}" for f in findings)


def _finding_line(finding: Finding) -> str:
    sources = ", ".join(r.as_ref() for r in finding.evidence if r.is_resolved) or "no source"
    return (
        f"[{finding.finding_id}] {finding.claim} "
        f"({finding.classification.value}, confidence {finding.confidence.value:.2f}; {sources})"
    )


def _rejected_line(finding: Finding) -> str:
    issues = (
        ", ".join(i.issue_type.value for i in finding.verification.issues)
        if finding.verification
        else ""
    )
    return f"[{finding.finding_id}] {finding.claim} (contradicted by evidence: {issues})"


def _evidence_lines(findings: list[Finding]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        for ref in finding.evidence:
            mark = "resolved" if ref.is_resolved else "UNRESOLVED"
            note = "" if ref.is_resolved else f" - {ref.resolution_note}"
            lines.append(f"[{finding.finding_id}] {ref.as_ref()} ({mark}){note}")
    return lines


def _confidence_line(finding: Finding) -> str:
    return f"[{finding.finding_id}] {finding.confidence.explain()}"


class ReportField(JarvisModel):
    """Placeholder kept for the renderer's typed access."""

    label: str = ""
    value: str = ""
