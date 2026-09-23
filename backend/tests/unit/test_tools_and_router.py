"""Phases 9 & 10 — the tool system and the router.

The security tests on `safe_eval` matter most: the specification forbids arbitrary code
execution, and these prove it is enforced by the parser rather than by string filtering.
"""

from __future__ import annotations

import pytest

from app.intelligence.router.engine import NoCapableToolError, ToolRouter
from app.llm.echo import EchoProvider
from app.schemas.common import FailureClass
from app.schemas.task import Task, TaskType
from app.schemas.tool import SelectionMode, ToolCall, ToolCapability
from app.tools.base import ToolContext, ToolRegistry, build_default_registry
from app.tools.builtin import (
    CalculatorTool,
    CsvAnalysisTool,
    DocumentExtractTool,
    DocumentSearchTool,
    UnsafeExpressionError,
    safe_eval,
)

REPORT = """Project Helix status report
Target completion date is 2026-04-30.
Approved budget is 380,000 for the migration phase.
Actual spend to date is 450,000.
"""

BUDGET_CSV = "item,amount\nmigration,450000\ntraining,25000\n"


def _ctx() -> ToolContext:
    return ToolContext(
        run_id="run_0123456789ab",
        task_id="task_001",
        document_ids=["report.txt", "budget.csv"],
        documents={"report.txt": REPORT, "budget.csv": BUDGET_CSV},
    )


def _task(task_type: TaskType, **inputs: object) -> Task:
    return Task(
        task_id="task_001",
        task_type=task_type,
        description=task_type.value,
        inputs=dict(inputs),
    )


# --- safe_eval: no arbitrary code execution ------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 2", 4.0),
        ("(450000 - 380000) / 380000", pytest.approx(0.18421, rel=1e-3)),
        ("-5 + 3", -2.0),
        ("2 ** 10", 1024.0),
        ("100 % 7", 2.0),
    ],
)
def test_arithmetic_evaluates(expression: str, expected: float) -> None:
    assert safe_eval(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").system("echo pwned")',
        "open('/etc/passwd').read()",
        "eval('2+2')",
        "[].__class__.__bases__",
        "lambda: 1",
        "x = 1",
        "print(1)",
        "2 ** 999999",
    ],
)
def test_anything_beyond_arithmetic_is_refused(expression: str) -> None:
    """Enforced by a node whitelist, not by pattern-matching the string.

    String filtering is defeatable; a whitelist of AST node types is not.
    """
    with pytest.raises(UnsafeExpressionError):
        safe_eval(expression)


def test_division_by_zero_is_a_refusal_not_a_crash() -> None:
    with pytest.raises(UnsafeExpressionError, match="division by zero"):
        safe_eval("1 / 0")


async def test_calculator_reports_unsafe_input_as_a_classified_failure() -> None:
    """Tools classify failures; they do not raise."""
    result = await CalculatorTool().execute(
        ToolCall(tool_name="calculator", arguments={"expression": "__import__('os')"}), _ctx()
    )
    assert result.failed
    assert result.error is not None
    assert result.error.failure_class is FailureClass.UNSAFE_EXPRESSION
    assert not result.is_retryable, "retrying an unsafe expression is pointless"


async def test_calculator_computes_a_percentage_difference() -> None:
    result = await CalculatorTool().execute(
        ToolCall(tool_name="calculator", arguments={"expression": "(450000-380000)/380000*100"}),
        _ctx(),
    )
    assert result.ok
    assert result.output["value"] == pytest.approx(18.42, rel=1e-2)


# --- document tools: every result carries a locator ----------------------------


async def test_search_returns_passages_with_locators() -> None:
    """An evidence reference that cannot be resolved to a location is worthless."""
    result = await DocumentSearchTool().execute(
        ToolCall(tool_name="document_search", arguments={"query": "budget approved"}), _ctx()
    )
    assert result.ok
    assert result.output["passages"]
    assert all(":r" in source for source in result.sources)


async def test_search_with_no_searchable_terms_fails_clearly() -> None:
    result = await DocumentSearchTool().execute(
        ToolCall(tool_name="document_search", arguments={"query": "a of"}), _ctx()
    )
    assert result.failed
    assert result.error is not None
    assert result.error.failure_class is FailureClass.MISSING_INPUT


async def test_extract_finds_dates_and_amounts_with_lines() -> None:
    result = await DocumentExtractTool().execute(
        ToolCall(tool_name="document_extract", arguments={"pattern": "dates and amounts"}),
        _ctx(),
    )
    assert result.ok
    kinds = {e["kind"] for e in result.output["extractions"]}
    values = {e["value"] for e in result.output["extractions"]}
    assert "date" in kinds and "amount" in kinds
    assert "2026-04-30" in values


async def test_csv_analysis_sums_a_column() -> None:
    result = await CsvAnalysisTool().execute(
        ToolCall(
            tool_name="csv_analysis", arguments={"document_id": "budget.csv", "column": "amount"}
        ),
        _ctx(),
    )
    assert result.ok
    assert result.output["rows"] == 2
    assert result.output["total"] == pytest.approx(475000.0)


async def test_a_missing_document_is_reported_not_guessed() -> None:
    result = await CsvAnalysisTool().execute(
        ToolCall(tool_name="csv_analysis", arguments={"document_id": "absent.csv"}), _ctx()
    )
    assert result.failed
    assert result.error is not None
    assert result.error.failure_class is FailureClass.NOT_FOUND


# --- registry ------------------------------------------------------------------


def test_the_default_registry_covers_every_capability_a_task_can_need() -> None:
    """A task type routing to a capability nothing serves is a latent runtime failure."""
    registry = build_default_registry()
    from app.schemas.task import TASK_CAPABILITY

    unserved = {
        capability for capability in TASK_CAPABILITY.values() if not registry.serving(capability)
    }
    # Verification is Member 4's; it arrives in Phase 15.
    assert unserved <= {ToolCapability.VERIFICATION}, f"unserved capabilities: {unserved}"


def test_registering_the_same_tool_twice_is_refused() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(CalculatorTool())


def test_the_catalogue_exports_schemas_for_prompt_injection() -> None:
    definition = next(d for d in build_default_registry().catalogue() if d.name == "calculator")
    assert "properties" in definition.input_schema
    assert definition.serves(ToolCapability.COMPUTATION)


# --- the router ----------------------------------------------------------------


async def test_a_single_candidate_is_chosen_deterministically() -> None:
    """Most selections never reach a model at all."""
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    selection = await ToolRouter(registry).route(_task(TaskType.EXTRACT_TIMELINE))

    assert selection.tool_name == "document_extract"
    assert selection.mode is SelectionMode.DETERMINISTIC
    assert selection.confidence == 1.0


async def test_no_capable_tool_raises_rather_than_dropping_the_task() -> None:
    """A silently dropped task produces a finding with invisibly missing support."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    with pytest.raises(NoCapableToolError):
        await ToolRouter(registry).route(_task(TaskType.EXTRACT_TIMELINE))


async def test_a_tie_is_broken_by_the_model_and_recorded_as_such() -> None:
    registry = build_default_registry()
    provider = EchoProvider(
        responses={"router": ['{"tool_name": "csv_analysis", "reason": "tabular"}']}
    )

    selection = await ToolRouter(registry, provider).route(_task(TaskType.CALCULATE_DIFFERENCE))

    assert selection.mode is SelectionMode.LLM_TIEBREAK
    assert selection.tool_name == "csv_analysis"
    assert len(selection.alternatives_considered) > 1
    assert selection.reason


async def test_without_a_provider_a_tie_falls_back_to_the_cheapest() -> None:
    registry = build_default_registry()
    selection = await ToolRouter(registry).route(_task(TaskType.CALCULATE_DIFFERENCE))

    assert selection.mode is SelectionMode.FALLBACK
    assert "lowest-cost" in selection.reason


async def test_a_tiebreak_naming_an_unavailable_tool_is_not_trusted() -> None:
    """An unregistered name would fail at dispatch, so it is never accepted."""
    registry = build_default_registry()
    provider = EchoProvider(responses={"router": ['{"tool_name": "imaginary_tool"}']})

    selection = await ToolRouter(registry, provider).route(_task(TaskType.CALCULATE_DIFFERENCE))

    assert selection.mode is SelectionMode.FALLBACK
    assert selection.tool_name in {t.name for t in registry.all()}


async def test_a_failed_tiebreak_falls_back_rather_than_failing_the_task() -> None:
    registry = build_default_registry()
    provider = EchoProvider(responses={"router": ["not json", "still not json", "no"]})

    selection = await ToolRouter(registry, provider).route(_task(TaskType.CALCULATE_DIFFERENCE))
    assert selection.mode is SelectionMode.FALLBACK


async def test_selection_is_recorded_on_the_timeline() -> None:
    from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
    from app.schemas.common import new_run_id
    from app.schemas.event import EventType

    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())

    await ToolRouter(registry).route(_task(TaskType.EXTRACT_BUDGET), emit=emitter)

    selected = memory.of_type(EventType.TOOL_SELECTED)
    assert len(selected) == 1
    assert selected[0].payload["tool"] == "document_extract"
    assert selected[0].payload["mode"] == "DETERMINISTIC"
    assert selected[0].payload["reason"], "every selection records why"


async def test_every_task_type_in_a_plan_can_be_routed() -> None:
    """End to end: the planner's vocabulary and the tool registry actually line up."""
    registry = build_default_registry()
    router = ToolRouter(registry)
    routable = 0

    for task_type in TaskType:
        try:
            await router.route(_task(task_type))
            routable += 1
        except NoCapableToolError:
            # Only verification is expected to be unserved until Phase 15.
            assert task_type is TaskType.VERIFY_FINDINGS

    assert routable >= len(TaskType) - 1
