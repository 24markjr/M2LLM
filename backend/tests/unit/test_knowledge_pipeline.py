"""Phase 30: the knowledge layer inside a mission.

The knowledge tool, the routing that reaches it, the knowledge pass the orchestrator adds for a
comparative objective (A5), and a whole mission on `EchoProvider` in which a finding cites both
sides of a knowledge-layer conflict.
"""

from __future__ import annotations

import json

import pytest

from app.core.agent_config import CrossSourcePass, KnowledgePolicy
from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.llm.echo import EchoProvider
from app.orchestration import mission as mission_module
from app.orchestration.mission import MissionStatus, run_mission
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.knowledge import (
    ClaimConflict,
    ConflictKind,
    ConflictSide,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeSnapshot,
)
from app.schemas.objective import Objective
from app.schemas.task import TASK_CAPABILITY, TaskType
from app.schemas.tool import ToolCall, ToolCapability
from app.tools.base import ToolContext, build_default_registry
from app.tools.knowledge import KnowledgeGraphTool

DOCS = {
    "report.txt": "Target completion is 30 April 2026.\nApproved budget 380,000.\n",
    "finance.txt": "Delivery completed 14 May 2026.\nTotal spend 450,000.\n",
}


def _claim(n: int, attribute: str, value: str, doc: str, line: int) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=f"CLM-{n:03d}",
        entity_id="ENT-001",
        attribute=attribute,
        value=value,
        source=f"{doc}:r{line}",
        document_id=doc,
        line=line,
    )


SNAPSHOT = KnowledgeSnapshot(
    entities=[
        KnowledgeEntity(entity_id="ENT-001", name="Project Aurora", entity_type=EntityType.OTHER)
    ],
    claims=[
        _claim(1, "completion_date", "30 April 2026", "report.txt", 1),
        _claim(2, "completion_date", "14 May 2026", "finance.txt", 1),
        _claim(3, "approved_budget", "380,000", "report.txt", 2),
    ],
    conflicts=[
        ClaimConflict(
            conflict_id="CON-001",
            entity_id="ENT-001",
            entity_name="Project Aurora",
            attribute="completion_date",
            kind=ConflictKind.DATE,
            sides=[
                ConflictSide(
                    value="30 April 2026", claim_ids=["CLM-001"], sources=["report.txt:r1"]
                ),
                ConflictSide(
                    value="14 May 2026", claim_ids=["CLM-002"], sources=["finance.txt:r1"]
                ),
            ],
        )
    ],
)


def _ctx(knowledge: KnowledgeSnapshot | None) -> ToolContext:
    return ToolContext(document_ids=list(DOCS), documents=DOCS, knowledge=knowledge)


# --- routing ---------------------------------------------------------------------------


def test_entities_and_claims_route_to_the_knowledge_graph_and_only_one_tool_serves_it() -> None:
    """Until Phase 30 these routed to a date-and-amount regex, which extracts neither."""
    assert TASK_CAPABILITY[TaskType.EXTRACT_ENTITIES] is ToolCapability.KNOWLEDGE_GRAPH
    assert TASK_CAPABILITY[TaskType.EXTRACT_CLAIMS] is ToolCapability.KNOWLEDGE_GRAPH
    serving = build_default_registry().serving(ToolCapability.KNOWLEDGE_GRAPH)
    assert [t.name for t in serving] == ["knowledge_graph"], "deterministic: no tiebreak needed"


# --- the tool ------------------------------------------------------------------------------


async def test_each_side_of_a_conflict_names_the_other_with_its_citation() -> None:
    result = await KnowledgeGraphTool().execute(
        ToolCall(tool_name="knowledge_graph", arguments={"mode": "conflicts"}), _ctx(SNAPSHOT)
    )
    assert result.ok
    items = result.output["extractions"]
    assert [(i["document_id"], i["line"], i["kind"]) for i in items] == [
        ("report.txt", 1, "conflict"),
        ("finance.txt", 1, "conflict"),
    ]
    assert items[0]["value"] == (
        "Project Aurora.completion_date = 30 April 2026 "
        "[conflicts with finance.txt:r1 = 14 May 2026]"
    )
    assert result.sources == ["report.txt:r1", "finance.txt:r1"]


async def test_all_mode_adds_the_other_grounded_claims_after_the_conflicts() -> None:
    result = await KnowledgeGraphTool().execute(
        ToolCall(tool_name="knowledge_graph", arguments={"mode": "all"}), _ctx(SNAPSHOT)
    )
    kinds = [i["kind"] for i in result.output["extractions"]]
    assert kinds == ["conflict", "conflict", "claim"]
    assert result.output["extractions"][2]["value"] == "Project Aurora.approved_budget = 380,000"


async def test_ungrounded_claims_are_never_handed_to_reasoning() -> None:
    invented = _claim(4, "spend", "999,999", "finance.txt", 2).model_copy(
        update={"grounded": False}
    )
    snapshot = SNAPSHOT.model_copy(update={"claims": [*SNAPSHOT.claims, invented]})
    result = await KnowledgeGraphTool().execute(
        ToolCall(tool_name="knowledge_graph", arguments={"mode": "all"}), _ctx(snapshot)
    )
    assert all("999,999" not in i["value"] for i in result.output["extractions"])


async def test_without_a_knowledge_base_the_tool_falls_back_to_regex_and_says_so() -> None:
    result = await KnowledgeGraphTool().execute(
        ToolCall(tool_name="knowledge_graph", arguments={"pattern": "dates"}), _ctx(None)
    )
    assert result.ok
    assert result.output["note"].startswith("knowledge layer not built")
    assert {i["kind"] for i in result.output["extractions"]} == {"date"}


# --- the knowledge pass ----------------------------------------------------------------------

COMPARATIVE = ["extract_timeline", "detect_inconsistencies"]
NOT_COMPARATIVE = ["extract_timeline"]


def _intent(operations: list[str]) -> str:
    return json.dumps(
        {
            "goal": "Compare the reports",
            "objective": "Find contradictions between the reports.",
            "operations": operations,
            "clarification_needed": False,
            "clarification_question": "",
        }
    )


def _plan(*types: str, first_id: int = 1) -> str:
    tasks = [
        {
            "id": f"task_{first_id + i:03d}",
            "type": kind,
            "description": kind,
            "depends_on": [] if i == 0 else [f"task_{first_id + i - 1:03d}"],
        }
        for i, kind in enumerate(types)
    ]
    return json.dumps({"tasks": tasks})


def _knowledge(claims: list[tuple[str, str, str, int]]) -> str:
    return json.dumps(
        {
            "entities": [{"name": "Project Aurora", "type": "OTHER"}],
            "relationships": [],
            "claims": [
                {"entity": e, "attribute": a, "value": v, "line": line} for e, a, v, line in claims
            ],
        }
    )


def _policy(monkeypatch: pytest.MonkeyPatch, mode: CrossSourcePass) -> None:
    policy = KnowledgePolicy(max_chunks=12, max_claims=400, cross_source_pass=mode)
    monkeypatch.setattr(mission_module, "get_knowledge_policy", lambda: policy)


COMPARE_TEXT = "Find contradictions between the reports."
TIMELINE_TEXT = "Extract the timeline from the reports."


async def _run(
    operations: list[str],
    plan: str,
    responses: dict[str, list[str]] | None = None,
    *,
    text: str = COMPARE_TEXT,
) -> tuple[object, MemoryEventSink]:
    memory = MemoryEventSink()
    provider = EchoProvider(
        responses={
            "intent": [_intent(operations)],
            "planner": [plan] * 4,
            "reasoning": [json.dumps({"findings": []})],
            **(responses or {}),
        },
        synthesize=True,
    )
    result = await run_mission(
        objective=Objective(text=text),
        documents=DOCS,
        provider=provider,
        emitter=RunEventEmitter(EventBus([memory]), new_run_id()),
        synthesize=False,
    )
    return result, memory


PLAN = _plan("extract_timeline", "detect_inconsistencies", "synthesize")


async def test_a_comparative_objective_gets_the_knowledge_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _policy(monkeypatch, CrossSourcePass.COMPARATIVE)
    result, memory = await _run(COMPARATIVE, PLAN)

    assert result.status is MissionStatus.COMPLETED  # type: ignore[attr-defined]
    added = result.knowledge_pass_task_id  # type: ignore[attr-defined]
    assert added == "task_004"
    task = next(t for t in result.plan.tasks if t.task_id == added)  # type: ignore[attr-defined]
    assert task.task_type is TaskType.EXTRACT_CLAIMS
    assert task.inputs == {"mode": "conflicts"}
    created = [e for e in memory.of_type(EventType.TASK_CREATED) if e.task_id == added]
    assert created and created[0].payload["origin"] == "knowledge_pass"
    assert memory.of_type(EventType.KNOWLEDGE_EXTRACTED)
    assert result.knowledge is not None  # type: ignore[attr-defined]
    assert result.knowledge_store == "memory"  # type: ignore[attr-defined]


async def test_the_pass_takes_the_next_free_id_not_the_task_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guard: the planner renumbers ids today, but the graph does not promise contiguous ids, and
    "count + 1" would collide with task_002 here."""
    from app.intelligence.graph.task_graph import TaskGraph
    from app.schemas.task import Task

    _policy(monkeypatch, CrossSourcePass.ALWAYS)
    graph = TaskGraph(
        [
            Task(task_id="task_002", task_type=TaskType.EXTRACT_TIMELINE, description="a"),
            Task(task_id="task_005", task_type=TaskType.SYNTHESIZE, description="b"),
        ]
    )
    added = await mission_module._add_knowledge_pass(graph, None, object())
    assert added == "task_006"
    assert graph.get("task_006") is not None


async def test_the_pass_does_not_change_plan_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Added after validation, so plan_validity measures the planner alone."""
    _policy(monkeypatch, CrossSourcePass.NEVER)
    without, _ = await _run(COMPARATIVE, PLAN)
    _policy(monkeypatch, CrossSourcePass.COMPARATIVE)
    with_pass, _ = await _run(COMPARATIVE, PLAN)
    assert with_pass.plan.validation == without.plan.validation  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("mode", "operations", "added"),
    [
        (CrossSourcePass.NEVER, COMPARATIVE, False),
        (CrossSourcePass.COMPARATIVE, NOT_COMPARATIVE, False),
        (CrossSourcePass.ALWAYS, NOT_COMPARATIVE, True),
    ],
)
async def test_the_policy_decides_when_the_pass_is_added(
    monkeypatch: pytest.MonkeyPatch, mode: CrossSourcePass, operations: list[str], added: bool
) -> None:
    _policy(monkeypatch, mode)
    text = COMPARE_TEXT if operations == COMPARATIVE else TIMELINE_TEXT
    plan = PLAN if operations == COMPARATIVE else _plan("extract_timeline", "synthesize")
    result, memory = await _run(operations, plan, text=text)
    assert result.status is MissionStatus.COMPLETED  # type: ignore[attr-defined]
    assert (result.knowledge_pass_task_id is not None) is added  # type: ignore[attr-defined]
    assert bool(memory.of_type(EventType.KNOWLEDGE_EXTRACTED)) is added


async def test_a_plan_that_already_reads_the_knowledge_base_gets_no_second_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _policy(monkeypatch, CrossSourcePass.COMPARATIVE)
    result, memory = await _run(
        COMPARATIVE,
        _plan("extract_timeline", "extract_claims", "detect_inconsistencies", "synthesize"),
    )
    assert result.status is MissionStatus.COMPLETED  # type: ignore[attr-defined]
    assert result.knowledge_pass_task_id is None  # type: ignore[attr-defined]
    assert len(memory.of_type(EventType.KNOWLEDGE_EXTRACTED)) == 1, "built once, for the plan"


async def test_a_finding_can_cite_both_sides_of_a_knowledge_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: the conflict reaches reasoning with both citations, and a finding that
    cites both survives the comparative rule with two resolved locators."""
    _policy(monkeypatch, CrossSourcePass.COMPARATIVE)
    claim = "The report gives 30 April 2026 and the finance file 14 May 2026 for completion."
    result, _ = await _run(
        COMPARATIVE,
        PLAN,
        {
            "knowledge": [
                _knowledge([("Project Aurora", "completion_date", "30 April 2026", 1)]),
                _knowledge([("Project Aurora", "completion_date", "14 May 2026", 1)]),
            ],
            "reasoning": [
                json.dumps(
                    {
                        "findings": [
                            {"claim": claim, "citations": ["report.txt:r1", "finance.txt:r1"]}
                        ]
                    }
                )
            ],
            "relevance": [json.dumps({"verdicts": [{"index": 1, "keep": True}]})],
            "verification": [json.dumps({"status": "SUPPORTED"})],
        },
    )

    knowledge = result.knowledge  # type: ignore[attr-defined]
    assert knowledge is not None and len(knowledge.conflicts) == 1
    pass_observation = next(
        o
        for o in result.observations
        if o.task_id == result.knowledge_pass_task_id  # type: ignore[attr-defined]
    )
    assert "[conflicts with finance.txt:r1 = 14 May 2026]" in json.dumps(
        pass_observation.structured
    )
    [finding] = result.findings  # type: ignore[attr-defined]
    assert finding.resolved_evidence_count == 2
