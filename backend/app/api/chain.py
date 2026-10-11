"""A finding's evidence chain (Phase 46): from claim to conclusion, each link with what it rests on.

Built from what the run already holds - the finding, its resolved citations and the text
verification read at each, the Evidence Locker item and authority of each document, what the
knowledge pass extracted from each cited line, the event that created the finding, the verifiers'
verdicts and the confidence factors. Nothing is computed afresh or asked of a model: the chain shows
the run.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.api.v1.schemas import ChainEvidence, ChainStep, FindingChain
from app.evidence.authority import label as authority_label
from app.evidence.authority import tier_for_name
from app.intelligence.confidence import why
from app.orchestration.mission import MissionResult
from app.schemas.event import EventType, ExecutionEvent
from app.schemas.finding import Finding
from app.schemas.knowledge import KnowledgeSnapshot


def _extractions(knowledge: KnowledgeSnapshot | None, locator: str) -> list[str]:
    if knowledge is None:
        return []
    names = {e.entity_id: e.name for e in knowledge.entities}
    return [
        f"{names.get(c.entity_id, c.entity_id)}.{c.attribute} = {c.value}"
        + ("" if c.grounded else " (not on its line - not used)")
        for c in knowledge.claims
        if c.source == locator
    ]


def finding_chain(
    run_id: str,
    finding: Finding,
    result: MissionResult,
    evidence: dict[str, str],
    authority: dict[str, str],
    events: Sequence[ExecutionEvent],
) -> FindingChain:
    citations: list[ChainEvidence] = []
    for ref in finding.evidence:
        locator = ref.as_ref()
        document = ref.locator.document_id
        tier = authority.get(document) or tier_for_name(document)[0]
        citations.append(
            ChainEvidence(
                locator=locator,
                document=document,
                resolved=ref.is_resolved,
                note=ref.resolution_note,
                evidence_id=evidence.get(document, ""),
                authority=authority_label(tier),
                text=result.evidence_text.get(locator, "") if ref.is_resolved else "",
                extractions=_extractions(result.knowledge, locator),
            )
        )

    created = next(
        (
            e
            for e in events
            if e.event_type is EventType.FINDING_CREATED and e.finding_id == finding.finding_id
        ),
        None,
    )
    origin = str(created.payload.get("origin", "")) if created else ""
    resolved = [c for c in citations if c.resolved]
    extracted = sum(len(c.extractions) for c in resolved)

    steps = [
        ChainStep(kind="CLAIM", title=finding.claim),
        ChainStep(
            kind="EVIDENCE",
            title=f"{len(resolved)} of {len(citations)} citation(s) resolved",
            detail="; ".join(
                f"{c.locator} ({c.evidence_id or 'no locker item'}, {c.authority})"
                for c in resolved
            )
            or "nothing it cites was read by the run",
        ),
        ChainStep(
            kind="EXTRACTION",
            title=f"{extracted} knowledge claim(s) extracted from the cited lines",
            detail="; ".join(x for c in resolved for x in c.extractions[:3]),
        ),
        ChainStep(
            kind="REASONING",
            title=(
                "from a contradiction the knowledge graph found (BUG-031)"
                if origin == "knowledge_conflict"
                else "proposed by reasoning over the run's observations"
            ),
            detail=(
                f"proposed as {finding.proposed_type}; ruled {finding.statement_type.value}"
                if finding.proposed_type
                else f"ruled {finding.statement_type.value}"
            )
            + f" on a {finding.statement_basis.value} basis"
            + (f"; revision {finding.revision}" if finding.revision else ""),
        ),
    ]
    verification = finding.verification
    if verification is None:
        steps.append(ChainStep(kind="VERIFICATION", title="not verified"))
    else:
        opinions = "; ".join(f"{o.verifier}: {o.status.value}" for o in verification.opinions)
        issues = "; ".join(f"{i.issue_type.value}: {i.description}" for i in verification.issues)
        steps.append(
            ChainStep(
                kind="VERIFICATION",
                title=f"{verification.status.value} ({verification.verifier}"
                + (", degraded" if verification.degraded else "")
                + ")",
                detail="; ".join(part for part in (opinions, issues) if part),
            )
        )
    steps.append(
        ChainStep(
            kind="CONCLUSION",
            title=f"{finding.statement_type.value}, confidence {finding.confidence.value:.2f}",
            detail=" ".join(why(finding)),
        )
    )
    return FindingChain(
        run_id=run_id, finding=finding, why=why(finding), evidence=citations, steps=steps
    )
