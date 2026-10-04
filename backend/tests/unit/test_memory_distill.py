"""Phase 33: what a finished run contributes to memory. Pure, no store.

The rules under test are the ones Member 4's memory did not have: only verified findings become
facts, facts carry their support instead of `confidence=1.0`, and episodes keep every finding
whatever its status.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.memory.distill import (
    episodes,
    known_entities,
    make_fact,
    memory_record,
    verified_facts,
    working_snapshot,
)
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding, FindingClassification
from app.schemas.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
)
from app.schemas.memory import Fact, FactKind, FactView
from app.schemas.objective import Objective
from app.schemas.plan import Plan
from app.schemas.task import Task, TaskType
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)


def _ref(source: str, *, resolved: bool = True) -> EvidenceRef:
    document, _, row = source.rpartition(":r")
    return EvidenceRef(
        locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
    )


def _verdict(status: VerificationStatus) -> VerificationResult:
    issues = (
        []
        if status is VerificationStatus.SUPPORTED
        else [VerificationIssue(issue_type=IssueType.EVIDENCE_MISMATCH, description="disagrees")]
    )
    return VerificationResult(status=status, confidence=0.9, issues=issues)


def _finding(
    fid: str,
    claim: str,
    sources: list[str],
    status: VerificationStatus | None,
    classification: FindingClassification = FindingClassification.FACT,
) -> Finding:
    return Finding(
        finding_id=fid,
        claim=claim,
        classification=classification,
        evidence=[_ref(s) for s in sources],
        verification=_verdict(status) if status else None,
    )


def _claim(n: int, entity: str, attribute: str, value: str, source: str, *, grounded: bool = True):
    return KnowledgeClaim(
        claim_id=f"CLM-{n:03d}",
        entity_id=entity,
        attribute=attribute,
        value=value,
        source=source,
        document_id=source.split(":")[0],
        line=1,
        grounded=grounded,
    )


ENTITIES = [
    KnowledgeEntity(entity_id="ENT-001", name="Rahul Sharma", entity_type=EntityType.PERSON),
    KnowledgeEntity(entity_id="ENT-002", name="ABC Logistics", entity_type=EntityType.ORG),
    KnowledgeEntity(entity_id="ENT-003", name="Shipment 4821", entity_type=EntityType.SHIPMENT),
]
SNAPSHOT = KnowledgeSnapshot(
    entities=ENTITIES,
    relationships=[
        KnowledgeRelationship(
            relationship_id="REL-001",
            subject_id="ENT-001",
            predicate="works_for",
            object_id="ENT-002",
            source="staff.txt:r3",
        ),
        KnowledgeRelationship(
            relationship_id="REL-002",
            subject_id="ENT-001",
            predicate="received",
            object_id="ENT-003",
            source="log.txt:r9",
        ),
    ],
    claims=[
        _claim(1, "ENT-003", "Arrival Date", "14 September", "a.txt:r1"),
        _claim(2, "ENT-003", "arrival_date", "16 September", "b.txt:r1"),
        _claim(3, "ENT-001", "shift", "night", "staff.txt:r3"),
        # Read by the model, not found in the text: never a fact, cited or not.
        _claim(4, "ENT-001", "badge", "B-17", "staff.txt:r3", grounded=False),
    ],
)

SUPPORTED = _finding(
    "F-001",
    "Rahul Sharma works night shifts for ABC Logistics.",
    ["staff.txt:r3"],
    VerificationStatus.SUPPORTED,
)
UNVERIFIED = _finding("F-002", "Shipment 4821 arrived on 14 September.", ["a.txt:r1"], None)
REJECTED = _finding(
    "F-003", "Rahul Sharma received shipment 4821.", ["log.txt:r9"], VerificationStatus.CONTRADICTED
)
HYPOTHESIS = _finding(
    "F-004",
    "The delay may have been caused by the night shift.",
    ["b.txt:r1"],
    VerificationStatus.UNSUPPORTED,
    FindingClassification.HYPOTHESIS,
)


def _result(
    run_id: str = "run_00000000a001", findings: list[Finding] | None = None
) -> MissionResult:
    tasks = [
        Task(
            task_id="task_001",
            task_type=TaskType.EXTRACT_ENTITIES,
            description="Extract the people",
        ),
        Task(
            task_id="task_002",
            task_type=TaskType.COMPARE_SOURCES,
            description="Compare the reports",
            created_by_revision=1,
        ),
    ]
    return MissionResult(
        run_id=run_id,
        objective=Objective(text="Who handled shipment 4821?"),
        status=MissionStatus.COMPLETED,
        plan=Plan(tasks=tasks),
        knowledge=SNAPSHOT,
        findings=findings
        if findings is not None
        else [SUPPORTED, UNVERIFIED, REJECTED, HYPOTHESIS],
    )


# --- working memory (T10) --------------------------------------------------------------------


def test_the_working_snapshot_is_read_off_the_result() -> None:
    started = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
    snapshot = working_snapshot(_result(), started)
    assert snapshot.investigation_id == "run_00000000a001"
    assert snapshot.objective == "Who handled shipment 4821?"
    # Includes the task the replanning loop inserted (created_by_revision=1).
    assert snapshot.plan_steps == ["Extract the people", "Compare the reports"]
    assert snapshot.hypotheses == ["The delay may have been caused by the night shift."]
    assert len(snapshot.findings) == 3
    assert snapshot.evidence_count == 0
    assert snapshot.started_at == started


# --- episodic memory (T11) -------------------------------------------------------------------


def test_every_finding_is_an_episode_whatever_its_status() -> None:
    logged = episodes(_result())
    assert [e.verification_status for e in logged] == [
        "SUPPORTED",
        "UNVERIFIED",
        "CONTRADICTED",
        "UNSUPPORTED",
    ]
    assert logged[0].episode_id == "run_00000000a001:F-001"
    assert logged[0].sources == ["staff.txt:r3"]
    assert {e.objective for e in logged} == {"Who handled shipment 4821?"}


def test_unresolved_citations_are_not_episode_sources() -> None:
    finding = _finding("F-009", "x", ["a.txt:r1"], VerificationStatus.SUPPORTED)
    finding.evidence.append(_ref("ghost.txt:r4", resolved=False))
    assert episodes(_result(findings=[finding]))[0].sources == ["a.txt:r1"]


# --- semantic memory (T12) -------------------------------------------------------------------


def test_only_lines_a_verified_finding_cites_become_facts() -> None:
    facts = verified_facts(
        "run_00000000a001", SNAPSHOT, [SUPPORTED, UNVERIFIED, REJECTED, HYPOTHESIS]
    )
    statements = sorted((f.kind, f.subject, f.predicate, f.object) for f in facts)
    # staff.txt:r3 is cited by the supported finding: its relationship and its grounded claim.
    # a.txt (unverified), log.txt (contradicted) and b.txt (an unsupported hypothesis) give none,
    # and the ungrounded badge claim on the cited line gives none either.
    assert statements == [
        (FactKind.ATTRIBUTE, "Rahul Sharma", "shift", "night"),
        (FactKind.RELATION, "Rahul Sharma", "works_for", "ABC Logistics"),
    ]
    assert all(f.support_count == 1 for f in facts)


def test_no_verified_finding_means_no_facts() -> None:
    assert verified_facts("run_00000000a001", SNAPSHOT, [UNVERIFIED, REJECTED]) == []


def test_the_same_statement_is_the_same_fact_across_runs_and_spellings() -> None:
    a = make_fact(FactKind.ATTRIBUTE, "Shipment 4821", "Arrival Date", "14 September")
    b = make_fact(FactKind.ATTRIBUTE, "the shipment 4821", "arrival_date", "14  september")
    c = make_fact(FactKind.ATTRIBUTE, "Shipment 4821", "arrival_date", "16 September")
    assert a.fact_id == b.fact_id != c.fact_id
    assert a.predicate == "arrival_date"
    rel = make_fact(FactKind.RELATION, "Rahul Sharma", "works_for", "ABC Logistics")
    assert rel.object_key == "abc logistics"


def test_a_fact_has_support_not_a_confidence() -> None:
    (fact, *_) = verified_facts("run_00000000a001", SNAPSHOT, [SUPPORTED])
    assert "confidence" not in fact.model_dump()
    assert fact.support_count == 1
    assert fact.runs == ["run_00000000a001"]
    view = FactView.of(fact).model_dump()
    assert view["support_count"] == 1 and "confidence" not in view


def test_a_fact_survives_its_own_round_trip() -> None:
    """Derived values are properties, so a stored fact re-validates (schemas.md, decision 5)."""
    for fact in verified_facts("run_00000000a001", SNAPSHOT, [SUPPORTED]):
        assert Fact.model_validate(fact.model_dump()) == fact
        assert Fact.model_validate_json(fact.model_dump_json()) == fact


def test_known_entities_are_keyed_by_normalised_name() -> None:
    known = known_entities("run_00000000a001", SNAPSHOT)
    assert [k.key for k in known] == ["rahul sharma", "abc logistics", "shipment 4821"]
    assert known[0].runs == ["run_00000000a001"]
    assert known[0].entity_types == [EntityType.PERSON]


def test_a_run_without_a_knowledge_base_still_leaves_episodes() -> None:
    result = _result()
    result.knowledge = None
    record = memory_record(result)
    assert len(record.episodes) == 4
    assert record.entities == [] and record.facts == []
    assert record.investigation.snapshot.objective == "Who handled shipment 4821?"
