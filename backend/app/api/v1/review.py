"""Human review of findings and the audit log, over HTTP (Phase 50).

A reviewer sees which findings need a decision and why, decides - approve, reject (with a reason,
optionally starting a follow-up investigation), or modify (with the reworded claim) - and every
decision is a new record. Approval releases the facts a finding cites into memory. The audit log
lists every write the API received and the system's own actions.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, status
from pydantic import Field

from app.api.errors import ApiError
from app.api.registry import MissionRecord, get_registry
from app.memory.service import remember_approved
from app.review.service import audit, get_review_store, requirements, review_of
from app.schemas.common import JarvisModel
from app.schemas.finding import Finding
from app.schemas.review import AuditEntry, FindingReview, ReviewDecision, ReviewState

router = APIRouter(tags=["review"])


class ReviewRequest(JarvisModel):
    state: ReviewState
    reason: str = Field(default="", max_length=2000)
    modified_claim: str = Field(default="", max_length=2000)
    # On a rejection: start a follow-up investigation of the same question in the same case.
    replan: bool = False


class ReviewResponse(JarvisModel):
    review: FindingReview
    # The follow-up investigation a rejection started, when it asked for one.
    follow_up_run_id: str = ""
    # Facts the approval released into memory.
    facts_remembered: int = 0


class ReviewList(JarvisModel):
    run_id: str
    store: str
    reviews: list[FindingReview] = Field(default_factory=list)

    @property
    def pending(self) -> int:
        return sum(1 for r in self.reviews if r.required and r.state is ReviewState.PENDING)


def _record(run_id: str) -> MissionRecord:
    record = get_registry().get(run_id)
    if record is None:
        raise ApiError(
            "MISSION_NOT_FOUND", f"no mission {run_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    return record


async def _reasons(record: MissionRecord, finding: Finding) -> list[str]:
    from app.api.registry import _case_severity

    challenge = record.challenges.get(finding.finding_id)
    return requirements(
        finding,
        case_severity=await _case_severity(record.case_id),
        challenge_outcome=challenge.outcome.value if challenge else "",
    )


@router.get("/missions/{run_id}/reviews", response_model=ReviewList)
async def get_reviews(run_id: str) -> ReviewList:
    """Every finding of a run: whether it needs review and why, its state and its decisions."""
    record = _record(run_id)
    findings = record.result.findings if record.result else []
    store = await get_review_store()
    decisions = await store.decisions(run_id)
    return ReviewList(
        run_id=run_id,
        store=store.name,
        reviews=[review_of(run_id, f, decisions, await _reasons(record, f)) for f in findings],
    )


@router.post("/missions/{run_id}/findings/{finding_id}/review", response_model=ReviewResponse)
async def review_finding(
    run_id: str,
    finding_id: str,
    body: ReviewRequest,
    reviewer: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> ReviewResponse:
    """Decide on a finding. REJECTED and MODIFIED need a reason; MODIFIED the reworded claim. Each
    decision is a new record - a changed mind does not erase the first."""
    record = _record(run_id)
    result = record.result
    finding = next(
        (f for f in (result.findings if result else []) if f.finding_id == finding_id), None
    )
    if result is None or finding is None:
        raise ApiError(
            "FINDING_NOT_FOUND",
            f"no finding {finding_id} in {run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if body.state is ReviewState.PENDING:
        raise ApiError(
            "REVIEW_STATE_INVALID",
            "a decision is APPROVED, REJECTED or MODIFIED; PENDING is where a finding starts",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        decision = ReviewDecision(
            run_id=run_id,
            finding_id=finding_id,
            state=body.state,
            reviewer=reviewer,
            reason=body.reason,
            modified_claim=body.modified_claim,
        )
    except ValueError as exc:
        raise ApiError(
            "REVIEW_INCOMPLETE", str(exc), status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        ) from exc

    store = await get_review_store()
    await store.decide(decision)
    await audit(
        f"review.{body.state.value.lower()}",
        actor=reviewer,
        target=f"{run_id}/{finding_id}",
        reason=body.reason,
        modified_claim=body.modified_claim,
    )

    remembered = 0
    if body.state in (ReviewState.APPROVED, ReviewState.MODIFIED) and finding.is_verified:
        remembered = await remember_approved(result, [finding_id])
        if remembered:
            await audit("memory.facts_released", target=f"{run_id}/{finding_id}", facts=remembered)

    follow_up = ""
    if body.state is ReviewState.REJECTED and body.replan:
        follow_up = await _follow_up(record, finding, body.reason, reviewer)

    decisions = await store.decisions(run_id)
    return ReviewResponse(
        review=review_of(run_id, finding, decisions, await _reasons(record, finding)),
        follow_up_run_id=follow_up,
        facts_remembered=remembered,
    )


async def _follow_up(record: MissionRecord, finding: Finding, reason: str, reviewer: str) -> str:
    """A rejection that asks for a replan starts a new investigation of the same question over the
    same documents, in the same case, told what was rejected and why."""
    from app.api.v1.missions import create_mission
    from app.api.v1.schemas import CreateMissionRequest

    objective = (
        f"{record.objective.text} (Follow-up: a reviewer rejected the finding "
        f'"{finding.claim[:300]}" because: {reason[:300]})'
    )[:2000]
    detail = await create_mission(
        CreateMissionRequest(
            objective=objective,
            documents=list(record.documents),
            case_id=record.case_id or None,
        )
    )
    await audit(
        "mission.follow_up",
        actor=reviewer,
        target=detail.run_id,
        rejected=f"{record.run_id}/{finding.finding_id}",
    )
    return detail.run_id


@router.get("/audit", response_model=list[AuditEntry])
async def get_audit(
    limit: int = Query(default=200, ge=1, le=2000),
    target: str = Query(default="", max_length=200),
) -> list[AuditEntry]:
    """The audit log, newest first: every write the API received and the system's own actions."""
    return await (await get_review_store()).audit(limit=limit, target=target)
