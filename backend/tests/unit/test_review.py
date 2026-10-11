"""Phase 50: human review of findings, and the audit log of every write.

Which findings need a person is set by rules; each decision is a new record with who, when and why;
approval releases a finding's facts into memory; a rejection can start a follow-up investigation;
and every write the API receives - accepted or refused - is in the audit log.
"""

from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import WRITE_METHODS, create_app
from app.api.registry import MissionRecord, get_registry
from app.memory.distill import memory_record
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.review.service import counts_as_established, get_review_store, requirements, review_of
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding, StatementType
from app.schemas.knowledge import KnowledgeClaim, KnowledgeEntity, KnowledgeSnapshot
from app.schemas.objective import Objective
from app.schemas.review import ReviewDecision, ReviewState
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)


def _finding(
    finding_id: str = "F-001",
    statement: StatementType = StatementType.SOURCE_CLAIM,
    issues: list[VerificationIssue] | None = None,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        claim="The budget is 250,000.",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id="a.txt", document_name="a.txt", row=4),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        statement_type=statement,
        statement_basis=StatementType.SOURCE_CLAIM,
        verification=VerificationResult(
            status=VerificationStatus.SUPPORTED, confidence=0.9, issues=issues or []
        ),
    )


# --- which findings need a person -----------------------------------------------------------------


def test_a_plain_verified_finding_needs_no_review_and_counts() -> None:
    finding = _finding()
    assert requirements(finding) == []
    assert counts_as_established(finding, review_of("run", finding, [], []))


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"statement": StatementType.CONTRADICTION}, "it reports a contradiction"),
        ({"statement": StatementType.RISK}, "it is a risk: a judgement"),
        (
            {
                "issues": [
                    VerificationIssue(
                        issue_type=IssueType.DESCRIBED_ONLY, description="described only"
                    )
                ]
            },
            "the verifier found it only described, not established",
        ),
    ],
)
def test_rules_say_why_a_finding_needs_review(kwargs: dict[str, object], reason: str) -> None:
    assert requirements(_finding(**kwargs)) == [reason]  # type: ignore[arg-type]


def test_a_high_case_or_a_contested_challenge_needs_review() -> None:
    assert requirements(_finding(), case_severity="HIGH") == ["its case is HIGH"]
    assert requirements(_finding(), case_severity="LOW") == []
    assert requirements(_finding(), challenge_outcome="CONTESTED") == ["a challenge contested it"]
    assert requirements(_finding(), attack_mapped=True) == ["it maps to a MITRE ATT&CK technique"]


def test_a_pending_finding_does_not_count_until_approved() -> None:
    finding = _finding(statement=StatementType.CONTRADICTION)
    reasons = requirements(finding)
    pending = review_of("run", finding, [], reasons)
    assert pending.state is ReviewState.PENDING and not counts_as_established(finding, pending)
    approved = review_of(
        "run",
        finding,
        [
            ReviewDecision(
                run_id="run", finding_id="F-001", state=ReviewState.APPROVED, reviewer="r"
            )
        ],
        reasons,
    )
    assert counts_as_established(finding, approved)


def test_a_rejection_or_a_modification_must_say_why() -> None:
    with pytest.raises(ValueError, match="must give its reason"):
        ReviewDecision(run_id="r", finding_id="F-001", state=ReviewState.REJECTED, reviewer="x")
    with pytest.raises(ValueError, match="reworded claim"):
        ReviewDecision(
            run_id="r", finding_id="F-001", state=ReviewState.MODIFIED, reviewer="x", reason="y"
        )


# --- memory: only what counts becomes a fact ------------------------------------------------------

SNAPSHOT = KnowledgeSnapshot(
    entities=[KnowledgeEntity(entity_id="ENT-1", name="Vega", entity_type="OTHER")],
    claims=[
        KnowledgeClaim(
            claim_id="CLM-1",
            entity_id="ENT-1",
            attribute="budget",
            value="250,000",
            source="a.txt:r4",
            document_id="a.txt",
            line=4,
        )
    ],
)


def test_a_finding_held_for_review_releases_no_fact() -> None:
    result = MissionResult(
        run_id=new_run_id(),
        objective=Objective(text="What is the budget?"),
        findings=[_finding()],
        knowledge=SNAPSHOT,
    )
    assert len(memory_record(result).facts) == 1
    held = memory_record(result, held={"F-001"})
    assert held.facts == []
    assert len(held.episodes) == 1, "the episode is still logged"


# --- the API --------------------------------------------------------------------------------------


def _mission(*findings: Finding) -> MissionRecord:
    record = MissionRecord(new_run_id(), Objective(text="What is the Vega budget?"), ["a.txt"])
    record.status = MissionStatus.COMPLETED
    record.stage = Stage.DONE
    record.result = MissionResult(
        run_id=record.run_id,
        objective=record.objective,
        status=MissionStatus.COMPLETED,
        findings=list(findings),
        knowledge=SNAPSHOT,
    )
    get_registry()._missions[record.run_id] = record
    return record


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_a_reviewer_decides_and_every_decision_is_kept() -> None:
    record = _mission(_finding(statement=StatementType.CONTRADICTION))
    url = f"/api/v1/missions/{record.run_id}"
    async with await _client() as client:
        before = (await client.get(f"{url}/reviews")).json()
        approved = await client.post(
            f"{url}/findings/F-001/review",
            json={"state": "APPROVED"},
            headers={"X-Jarvis-User": "reviewer-2"},
        )
        rejected = await client.post(
            f"{url}/findings/F-001/review",
            json={"state": "REJECTED", "reason": "the finance sheet was superseded"},
            headers={"X-Jarvis-User": "reviewer-3"},
        )
        incomplete = await client.post(
            f"{url}/findings/F-001/review", json={"state": "MODIFIED", "reason": "x"}
        )
        audit = (await client.get("/api/v1/audit", params={"target": record.run_id})).json()

    [review] = before["reviews"]
    assert review["required"] and review["state"] == "PENDING"
    assert review["required_because"] == ["it reports a contradiction"]
    assert approved.status_code == 200
    body = rejected.json()["review"]
    assert body["state"] == "REJECTED"
    assert [(d["state"], d["reviewer"]) for d in body["history"]] == [
        ("APPROVED", "reviewer-2"),
        ("REJECTED", "reviewer-3"),
    ]
    assert incomplete.status_code == 422
    assert incomplete.json()["error_code"] == "REVIEW_INCOMPLETE"
    actions = [e["action"] for e in audit]
    assert "review.approved" in actions and "review.rejected" in actions


async def test_a_rejection_can_start_a_follow_up_investigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1 import missions as mission_routes
    from app.api.v1.schemas import CreateMissionRequest, MissionDetail

    started: list[CreateMissionRequest] = []

    async def fake_create(body: CreateMissionRequest) -> MissionDetail:
        started.append(body)
        return MissionDetail.model_validate(
            {
                "run_id": "run_00000000f011",
                "objective": body.objective,
                "status": "PENDING",
                "stage": "UNDERSTANDING",
                "created_at": "2026-10-11T00:00:00Z",
            }
        )

    monkeypatch.setattr(mission_routes, "create_mission", fake_create)
    record = _mission(_finding())
    async with await _client() as client:
        response = await client.post(
            f"/api/v1/missions/{record.run_id}/findings/F-001/review",
            json={"state": "REJECTED", "reason": "wrong year", "replan": True},
        )
    assert response.json()["follow_up_run_id"] == "run_00000000f011"
    [request] = started
    assert request.documents == ["a.txt"]
    assert "rejected the finding" in request.objective and "wrong year" in request.objective


async def test_every_write_route_is_audited_refused_or_not() -> None:
    """The middleware's promise, checked route by route: a new write route cannot slip past."""
    app = create_app()
    # From the OpenAPI schema: the routes the app serves, whatever router nests them.
    writes = [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in WRITE_METHODS
    ]
    assert len(writes) >= 10
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in writes:
            concrete = re.sub(r"\{[^}]+\}", "x-unknown", path)
            response = await client.request(
                method, concrete, json=None, headers={"X-Jarvis-User": "auditor-test"}
            )
            assert response.status_code != 500, (method, path, response.text[:200])
    entries = await (await get_review_store()).audit(limit=2000)
    audited = {e.action for e in entries if e.actor == "auditor-test"}
    missing = [
        (m, p) for m, p in writes if f"{m} {re.sub(r'{[^}]+}', 'x-unknown', p)}" not in audited
    ]
    assert missing == []
