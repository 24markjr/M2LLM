"""Following an investigation up (v4 Phase 3b).

    POST /missions/{run_id}/clarify                         answer a clarifying question: the same
                                                            documents and case, the answer added
    POST /missions/{run_id}/rerun                           the question again, or an edited one
    GET  /missions/{run_id}/findings/{finding_id}/history   every recorded change to a finding
    GET  /cases/{case_id}/compare?a=run_x&b=run_y           what changed between two runs of a case
    GET  /cases/{case_id}/stale                             findings older than the case's evidence

Nothing here changes a finding. History is assembled from what the run and the case already record -
events, the verifier's verdict, reviews, challenges, the conversation's re-checks - so it cannot
disagree with them.
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Header, Query, status
from pydantic import Field

from app.api.errors import ApiError, MissionNotFoundError
from app.api.registry import MissionRecord, get_registry
from app.api.v1.schemas import CreateMissionRequest, MissionDetail
from app.cases.service import get_case_store
from app.conversation import store as conversations
from app.evidence.service import get_locker
from app.intelligence.context.hybrid import terms
from app.orchestration.mission import MissionStatus
from app.review.service import audit, get_review_store
from app.schemas.common import JarvisModel
from app.schemas.event import EventType
from app.schemas.finding import Finding

missions = APIRouter(prefix="/missions", tags=["follow-up"])
cases = APIRouter(prefix="/cases", tags=["follow-up"])


# --- answering a clarifying question -------------------------------------------------------------


class Clarification(JarvisModel):
    answer: str = Field(min_length=1, max_length=2000)


@missions.post("/{run_id}/clarify", response_model=MissionDetail, status_code=202)
async def clarify(
    run_id: str,
    body: Clarification,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> MissionDetail:
    """A run that stopped to ask a question is answered by starting it again with the answer: the
    same documents, case and mode, the person's answer added to the objective."""
    from app.api.v1.missions import create_mission

    record = _record(run_id)
    if record.status is not MissionStatus.CLARIFICATION_NEEDED:
        raise ApiError(
            "NOT_ASKING",
            f"{run_id} did not stop to ask a question",
            status_code=status.HTTP_409_CONFLICT,
        )
    objective = f"{record.objective.text.strip()}\n\nClarification: {body.answer.strip()}"
    detail = await create_mission(
        CreateMissionRequest(
            objective=objective[:2000],
            documents=list(record.documents),
            case_id=record.case_id or None,
            mode=record.objective.mode,
        )
    )
    await audit("mission.clarified", actor=actor, target=detail.run_id, answers=run_id)
    return detail


# --- running it again (v4 Phase 4) ---------------------------------------------------------------


class Rerun(JarvisModel):
    # Empty: the same question again (regenerate). Otherwise the edited question (a branch).
    objective: str = Field(default="", max_length=2000)


@missions.post("/{run_id}/rerun", response_model=MissionDetail, status_code=202)
async def rerun(
    run_id: str,
    body: Rerun,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> MissionDetail:
    """Run an investigation again on the same documents and case - the same question, or an edited
    one. The first run is untouched; compare the two with `GET /cases/{case_id}/compare`."""
    from app.api.v1.missions import create_mission

    record = _record(run_id)
    if not record.is_finished():
        raise ApiError(
            "STILL_RUNNING",
            f"{run_id} is still running; stop it or wait for it",
            status_code=status.HTTP_409_CONFLICT,
        )
    objective = body.objective.strip() or record.objective.text
    detail = await create_mission(
        CreateMissionRequest(
            objective=objective,
            documents=list(record.documents),
            case_id=record.case_id or None,
            mode=record.objective.mode,
        )
    )
    await audit(
        "mission.rerun",
        actor=actor,
        target=detail.run_id,
        of=run_id,
        edited=bool(body.objective.strip()),
    )
    return detail


# --- a finding's history -------------------------------------------------------------------------


class HistoryEntry(JarvisModel):
    at: datetime | None = None
    kind: str  # created, verified, rejected, reviewed, challenged, rechecked
    summary: str
    by: str = "system"


class FindingHistory(JarvisModel):
    run_id: str
    finding_id: str
    claim: str
    entries: list[HistoryEntry] = Field(default_factory=list)


@missions.get("/{run_id}/findings/{finding_id}/history", response_model=FindingHistory)
async def history(run_id: str, finding_id: str) -> FindingHistory:
    record = _record(run_id)
    finding = _finding(record, finding_id)
    entries: list[HistoryEntry] = []
    for event in record.events:
        if event.finding_id != finding_id:
            continue
        payload = event.payload
        if event.event_type is EventType.FINDING_CREATED:
            how = " (cited by its values)" if payload.get("cited_by_values") else ""
            entries.append(
                HistoryEntry(
                    at=event.timestamp,
                    kind="created",
                    summary=f"proposed citing {payload.get('cited', 0)} line(s){how}",
                )
            )
        elif event.event_type in (EventType.FINDING_VERIFIED, EventType.FINDING_REJECTED):
            opinions = payload.get("opinions") or {}
            said = ", ".join(f"{k} {str(v).lower()}" for k, v in dict(opinions).items())
            entries.append(
                HistoryEntry(
                    at=event.timestamp,
                    kind="verified"
                    if event.event_type is EventType.FINDING_VERIFIED
                    else "rejected",
                    summary=f"{str(payload.get('status', '')).lower()}"
                    + (f" ({said})" if said else ""),
                )
            )
    for decision in await (await get_review_store()).decisions(run_id):
        if decision.finding_id == finding_id:
            entries.append(
                HistoryEntry(
                    at=decision.at,
                    kind="reviewed",
                    summary=decision.state.value.lower()
                    + (f": {decision.reason}" if decision.reason else ""),
                    by=decision.reviewer,
                )
            )
    challenge = record.challenges.get(finding_id)
    if challenge is not None:
        entries.append(
            HistoryEntry(
                at=challenge.challenged_at,
                kind="challenged",
                summary=f"{challenge.outcome.value.lower()}: {challenge.summary}",
                by=challenge.challenged_by,
            )
        )
    if record.case_id:
        for turn in conversations.load(record.case_id).turns:
            for check in turn.rechecks:
                if check.run_id == run_id and check.finding_id == finding_id:
                    entries.append(
                        HistoryEntry(
                            at=turn.created_at,
                            kind="rechecked",
                            summary=f"{check.before.lower()} -> {check.after.lower()}"
                            + (f": {check.reason}" if check.reason else ""),
                        )
                    )
    entries.sort(key=lambda e: (e.at is None, e.at or datetime.min))
    return FindingHistory(
        run_id=run_id, finding_id=finding_id, claim=finding.claim, entries=entries
    )


# --- run-to-run comparison -----------------------------------------------------------------------


class Pair(JarvisModel):
    a: str = ""  # finding id in run a
    b: str = ""  # finding id in run b
    claim_a: str = ""
    claim_b: str = ""
    status_a: str = ""
    status_b: str = ""
    change: str  # same, status changed, only in a, only in b


class RunComparison(JarvisModel):
    case_id: str
    a: str
    b: str
    pairs: list[Pair] = Field(default_factory=list)


def _status(finding: Finding) -> str:
    return finding.verification.status.value if finding.verification else "UNVERIFIED"


def _similar(x: str, y: str) -> float:
    a, b = set(terms(x)), set(terms(y))
    return len(a & b) / len(a | b) if a | b else 0.0


@cases.get("/{case_id}/compare", response_model=RunComparison)
async def compare(
    case_id: str,
    a: str = Query(pattern=r"^run_[0-9a-f]{12}$"),
    b: str = Query(pattern=r"^run_[0-9a-f]{12}$"),
) -> RunComparison:
    """Findings of two runs of the case, paired by what they claim (shared words, Jaccard >= 0.5):
    unchanged, changed status, or found by only one run."""
    first, second = _record(a), _record(b)
    if case_id not in (first.case_id, second.case_id) or first.case_id != second.case_id:
        raise ApiError(
            "NOT_IN_CASE",
            f"{a} and {b} are not both investigations of {case_id}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    left = list(first.result.findings) if first.result else []
    right = list(second.result.findings) if second.result else []
    pairs: list[Pair] = []
    unmatched = list(right)
    for finding in left:
        best = max(unmatched, key=lambda f: _similar(finding.claim, f.claim), default=None)
        if best is not None and _similar(finding.claim, best.claim) >= 0.5:
            unmatched.remove(best)
            same = _status(finding) == _status(best)
            pairs.append(
                Pair(
                    a=finding.finding_id,
                    b=best.finding_id,
                    claim_a=finding.claim,
                    claim_b=best.claim,
                    status_a=_status(finding),
                    status_b=_status(best),
                    change="same" if same else "status changed",
                )
            )
        else:
            pairs.append(
                Pair(
                    a=finding.finding_id,
                    claim_a=finding.claim,
                    status_a=_status(finding),
                    change="only in a",
                )
            )
    pairs += [
        Pair(b=f.finding_id, claim_b=f.claim, status_b=_status(f), change="only in b")
        for f in unmatched
    ]
    return RunComparison(case_id=case_id, a=a, b=b, pairs=pairs)


# --- evidence added after a finding ---------------------------------------------------------------


class StaleFinding(JarvisModel):
    run_id: str
    finding_id: str
    claim: str
    finished_at: datetime
    newer_evidence: list[str] = Field(default_factory=list)


@cases.get("/{case_id}/stale", response_model=list[StaleFinding])
async def stale(case_id: str) -> list[StaleFinding]:
    """Findings of runs that finished before evidence was added to the case: the new files were not
    read when they were checked, so they are marked for re-checking ("recheck F-002")."""
    store = await get_case_store()
    links = await store.evidence(case_id)
    locker = await get_locker()
    names: dict[str, str] = {}
    for link in links:
        item = await locker.get(link.evidence_id)
        names[link.evidence_id] = item.name if item is not None else link.evidence_id
    marked: list[StaleFinding] = []
    registry = get_registry()
    for investigation in await store.investigations(case_id):
        record = registry.get(investigation.run_id)
        if record is None or record.result is None or record.finished_at is None:
            continue
        finished = record.finished_at
        newer = sorted(
            names[link.evidence_id]
            for link in links
            if link.added_at > finished and names[link.evidence_id] not in record.documents
        )
        if newer:
            marked += [
                StaleFinding(
                    run_id=record.run_id,
                    finding_id=f.finding_id,
                    claim=f.claim,
                    finished_at=finished,
                    newer_evidence=newer,
                )
                for f in record.result.findings
            ]
    return marked


# --- helpers -------------------------------------------------------------------------------------


def _record(run_id: str) -> MissionRecord:
    record = get_registry().get(run_id) if re.fullmatch(r"run_[0-9a-f]{12}", run_id) else None
    if record is None:
        raise MissionNotFoundError(run_id)
    return record


def _finding(record: MissionRecord, finding_id: str) -> Finding:
    finding = next(
        (
            f
            for f in (record.result.findings if record.result else [])
            if f.finding_id == finding_id
        ),
        None,
    )
    if finding is None:
        raise ApiError(
            "FINDING_NOT_FOUND",
            f"no finding {finding_id} in {record.run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return finding
