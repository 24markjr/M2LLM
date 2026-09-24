"""The evaluation runner.

Executes each scenario through the *real* pipeline — intent, planner, router, execution,
reasoning, verification, gap detection, replanning — and scores what comes out. There is no
mock path and no shortcut: a harness that measured a simplified pipeline would be measuring
something nobody ships.

Scenarios are loaded from `.agent/evals/datasets/`. Ground truth lives with them, because
an expectation kept apart from the case it describes drifts from it.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from app.core.agent_config import get_models_config
from app.core.config import get_settings
from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.core.logging import get_logger
from app.evaluation.metrics import (
    MetricSet,
    ScenarioExpectation,
    ScenarioOutcome,
    aggregate,
    claims_found,
    negative_case_score,
    score_scenario,
)
from app.evaluation.report import EvalReport, ScenarioReport, config_hash
from app.integrations.verification import build_verification_provider
from app.intelligence.execution.engine import ExecutionEngine
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.intent.engine import IntentEngine
from app.intelligence.planner.engine import PlanInvalidError, Planner
from app.intelligence.reasoning.engine import ReasoningEngine
from app.intelligence.replanning.controller import ReplanningController
from app.intelligence.router.engine import ToolRouter
from app.llm import get_provider
from app.llm.prompts import get_prompt_library
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.intent import Operation
from app.schemas.objective import AttachedDocument, Objective, ObjectiveScope
from app.tools.base import ToolContext, build_default_registry
from app.tools.loader import load_documents

log = get_logger(__name__)


def datasets_dir() -> Path:
    return get_settings().agent_dir / "evals" / "datasets"


def reports_dir() -> Path:
    return get_settings().agent_dir / "evals" / "reports"


def load_expectations(suite: str = "all") -> list[ScenarioExpectation]:
    """Load scenario ground truth. `all` loads everything in the dataset directory."""
    directory = datasets_dir()
    if not directory.exists():
        return []

    expectations: list[ScenarioExpectation] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        if suite != "all" and suite not in (raw.get("suites") or []):
            continue
        expectations.append(_parse(raw, path.stem))
    return expectations


def _as_int(raw: dict[str, object], key: str, default: int) -> int:
    value = raw.get(key)
    return int(value) if isinstance(value, int | float | str) and str(value).strip() else default


def _as_str_list(raw: dict[str, object], key: str) -> list[str]:
    value = raw.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


def _as_str_dict(raw: dict[str, object], key: str) -> dict[str, str]:
    value = raw.get(key)
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def _parse(raw: dict[str, object], fallback_id: str) -> ScenarioExpectation:
    operations: list[Operation] = []
    for name in _as_str_list(raw, "expected_operations"):
        try:
            operations.append(Operation(name))
        except ValueError:
            log.warning("unknown_expected_operation", operation=name)

    raw_edges = raw.get("expected_edges")
    edges = [
        (str(pair[0]), str(pair[1]))
        for pair in (raw_edges if isinstance(raw_edges, list) else [])
        if isinstance(pair, list | tuple) and len(pair) == 2
    ]

    return ScenarioExpectation(
        scenario_id=str(raw.get("id") or fallback_id),
        objective=str(raw.get("objective") or ""),
        documents=_as_str_list(raw, "documents"),
        expected_operations=operations,
        min_tasks=_as_int(raw, "min_tasks", 2),
        expected_edges=edges,
        expected_tools=_as_str_dict(raw, "expected_tools"),
        expected_claims=_as_str_list(raw, "expected_claims"),
        expect_zero_findings=bool(raw.get("expect_zero_findings") or False),
        minimal_tasks=_as_int(raw, "minimal_tasks", 0),
    )


def _resolve(name: str) -> Path:
    root = get_settings().agent_dir / "fixtures"
    for candidate in (root / "documents" / name, root / "csv" / name, Path(name)):
        if candidate.exists():
            return candidate
    return Path(name)


async def run_scenario(expectation: ScenarioExpectation) -> ScenarioOutcome:
    """Execute one scenario through the real pipeline and collect what it produced."""
    started = time.perf_counter()
    provider = get_provider()
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())

    documents, loaded = load_documents([_resolve(d) for d in expectation.documents])
    page_starts = {d.document_id: d.page_starts for d in loaded if d.page_starts}

    objective = Objective(
        text=expectation.objective,
        scope=ObjectiveScope(
            documents=[AttachedDocument(document_id=name, name=name) for name in documents]
        ),
    )

    outcome = ScenarioOutcome(scenario_id=expectation.scenario_id)

    try:
        outcome.intent = await IntentEngine(provider).analyze(objective, emit=emitter)

        plan = await Planner(provider).create_plan(outcome.intent, objective, emit=emitter)
        outcome.plan = plan

        registry = build_default_registry()
        router = ToolRouter(registry, provider)
        graph = TaskGraph.from_plan(plan)
        ctx = ToolContext(
            run_id=emitter.run_id,
            document_ids=list(documents),
            documents=documents,
            page_starts=page_starts,
        )

        observations = await ExecutionEngine(graph, registry, router, emit=emitter).run(ctx)

        result = await ReplanningController(
            graph=graph,
            registry=registry,
            router=router,
            reasoner=ReasoningEngine(provider),
            verifier=build_verification_provider(provider),
            emit=emitter,
        ).run(objective, observations, ctx)

        outcome.findings = result.findings
        outcome.gaps = result.gaps
        outcome.replan_iterations = result.iterations
        # The plan carries the executed graph's state, so routing and status are scored
        # against what actually ran rather than what was planned.
        outcome.plan = plan.model_copy(update={"tasks": graph.tasks})

    except PlanInvalidError as exc:
        outcome.error = f"PLAN_INVALID: {exc}"
    except Exception as exc:  # noqa: BLE001 - one bad scenario must not end the suite
        log.error("scenario_failed", scenario=expectation.scenario_id, error=str(exc))
        outcome.error = f"{type(exc).__name__}: {exc}"

    calls = sink.of_type(EventType.LLM_CALL_COMPLETED)
    outcome.llm_calls = len(calls)
    outcome.repair_attempts = sum(int(c.payload.get("repair_attempt", 0) or 0) for c in calls)
    outcome.latency_s = time.perf_counter() - started
    return outcome


async def run_suite(suite: str = "all") -> EvalReport:
    """Run every scenario in a suite and produce a stamped report."""
    expectations = load_expectations(suite)
    settings = get_settings()

    report = EvalReport(
        suite=suite,
        model=settings.ollama_model,
        config_hash=config_hash(
            {
                "temperature": settings.llm_temperature,
                "seed": settings.llm_seed,
                "max_replan_iterations": settings.max_replan_iterations,
                "max_parallel_tasks": settings.max_parallel_tasks,
                "planning_policy": settings.planning_policy.value,
                "structured_max_repairs": get_models_config().structured_output.max_repairs,
            }
        ),
    )

    scores: list[MetricSet] = []
    for expectation in expectations:
        log.info("scenario_started", scenario=expectation.scenario_id)
        outcome = await run_scenario(expectation)
        metrics = score_scenario(expectation, outcome)
        scores.append(metrics)

        report.scenarios.append(
            ScenarioReport(
                scenario_id=expectation.scenario_id,
                metrics=metrics,
                findings=len(outcome.findings),
                gaps=len(outcome.gaps),
                gaps_closed=sum(1 for g in outcome.gaps if g.resolved),
                error=outcome.error,
                is_negative_case=expectation.expect_zero_findings,
                negative_case_passed=negative_case_score(expectation, outcome) == 1.0,
                confabulated_claims=(
                    [f.claim for f in outcome.findings] if expectation.expect_zero_findings else []
                ),
                is_positive_case=bool(expectation.expected_claims),
                expected_claims_found=claims_found(expectation, outcome),
            )
        )

    report.aggregate = aggregate(scores)
    # Stamp only the prompts actually loaded during the run.
    report.prompt_versions = get_prompt_library().versions()
    return report
