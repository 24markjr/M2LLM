"""JARVIS command line — the demonstration entry point.

    python -m app.cli investigate "Find inconsistencies between the timeline and budget."
    python -m app.cli intent "..." --docs project_report.pdf budget.csv
    python -m app.cli health

Output is ASCII only: the Windows console defaults to cp1252 (BUG-001).

What this shows is deliberately *operational*: the objective going in, the timeline of what
the agent did, and the structures coming out. It never shows model deliberation (invariant
#3) - what you see is what the system decided, not what it was thinking.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.core.logging import configure_logging
from app.evaluation.report import LOWER_IS_BETTER, compare, load_latest, write_report
from app.evaluation.runner import reports_dir, run_suite
from app.intelligence.intent.engine import IntentEngine, derive_operations
from app.intelligence.planner.engine import execution_levels
from app.intelligence.router.engine import NoCapableToolError, ToolRouter
from app.intelligence.synthesis.renderers import to_markdown, to_text
from app.llm import get_provider
from app.orchestration.mission import MissionResult, MissionStatus, Stage, run_mission
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.objective import AttachedDocument, DocumentKind, Objective, ObjectiveScope
from app.schemas.plan import Plan
from app.schemas.task import TaskStatus
from app.tools.base import build_default_registry
from app.tools.loader import load_documents

RULE = "-" * 78

_KIND_BY_SUFFIX = {
    "pdf": DocumentKind.PDF,
    "csv": DocumentKind.CSV,
    "txt": DocumentKind.TEXT,
    "md": DocumentKind.MARKDOWN,
    "json": DocumentKind.JSON,
}


def _build_objective(text: str, docs: list[str]) -> Objective:
    attached = [
        AttachedDocument(
            document_id=name,
            name=name,
            kind=_KIND_BY_SUFFIX.get(name.rsplit(".", 1)[-1].lower(), DocumentKind.UNKNOWN),
        )
        for name in docs
    ]
    return Objective(text=text, scope=ObjectiveScope(documents=attached))


def _resolve(name: str) -> Path:
    """Find a document by path, or by name inside .agent/fixtures/."""
    direct = Path(name)
    if direct.exists():
        return direct

    root = get_settings().agent_dir / "fixtures"
    for candidate in (root / "documents" / name, root / "csv" / name, root / name):
        if candidate.exists():
            return candidate
    return direct


def _load_documents(names: list[str]) -> tuple[dict[str, str], dict[str, list[int]]]:
    """Load the run's documents, with the page map that makes PDF citations checkable."""
    documents, loaded = load_documents([_resolve(n) for n in names])
    page_starts = {d.document_id: d.page_starts for d in loaded if d.page_starts}
    return documents, page_starts


def _print_documents(names: list[str]) -> list[str]:
    """Show what was actually loaded, so a partial read is never mistaken for a full one."""
    _, loaded = load_documents([_resolve(n) for n in names])
    missing = set(names) - {d.document_id for d in loaded}

    print()
    print(f"documents loaded ({len(loaded)}):")
    for document in loaded:
        flag = "  [PARTIAL]" if document.truncated else ""
        print(f"  - {document.document_id}  {document.kind}, {document.summary}{flag}")
    for name in sorted(missing):
        print(f"  - {name}  COULD NOT BE READ - excluded from this investigation")
    return [d.document_id for d in loaded]


def _print_header(title: str, run_id: str, model: str, text: str, docs: list[str]) -> None:
    print()
    print(RULE)
    print(title)
    print(RULE)
    print(f"run       : {run_id}")
    print(f"model     : {model}")
    print(f"objective : {text}")
    print(f"documents : {', '.join(docs) if docs else '(none)'}")


def _print_trace(sink: MemoryEventSink, run_id: str) -> None:
    print()
    print(RULE)
    print("EXECUTION TRACE")
    print(RULE)
    for event in sink.for_run(run_id):
        print(f"  {event.describe()}")


async def run_intent(text: str, docs: list[str]) -> int:
    provider = get_provider()
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    objective = _build_objective(text, docs)

    _print_header("JARVIS - INTENT ANALYSIS", emitter.run_id, provider.model_id, text, docs)

    # The deterministic pre-pass, shown separately so the split between what the system
    # derives structurally and what the model contributes is visible.
    heuristic = derive_operations(objective)
    print(f"\npre-pass  : {len(heuristic)} operation(s) derived without the model")
    for op in sorted(heuristic, key=lambda o: o.value):
        print(f"            - {op.value}")

    await emitter.emit(EventType.RUN_STARTED, payload={"objective": text})
    print("\nanalysing ...")
    intent = await IntentEngine(provider).analyze(objective, emit=emitter)
    await emitter.emit(EventType.RUN_COMPLETED)

    _print_trace(sink, emitter.run_id)

    print()
    print(RULE)
    print("INTENT")
    print(RULE)
    print(f"goal            : {intent.goal}")
    print(f"objective       : {intent.objective}")
    print(f"output format   : {intent.output_format.value}")
    print(f"evidence needed : {intent.constraints.evidence_required}")

    print(f"\nrequired operations ({len(intent.required_operations)}):")
    for required in intent.required_operations:
        print(f"  - {required.operation.value}")

    if intent.unsupported_operations:
        print(f"\nunsupported ({len(intent.unsupported_operations)}):")
        for unsupported in intent.unsupported_operations:
            print(f"  - {unsupported.requested}  [{unsupported.reason}]")

    if intent.clarification_needed:
        print("\nCLARIFICATION NEEDED")
        print(f"  {intent.clarification_question}")
        print("  (an ambiguous objective must not produce a confident plan)")

    _print_llm_stats(sink)
    print(RULE)
    print()
    return 0


async def run_investigate(text: str, docs: list[str], report_path: str = "") -> int:
    """The end-to-end demo: objective in, evidence-backed report out.

    This function renders a run. It does not assemble one - `app/orchestration/mission.py` owns the
    pipeline, and the API and the web console render the same `MissionResult`. Three copies of that
    sequence used to exist, and a fix applied to one silently did not apply to the others.
    """
    provider = get_provider()
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    objective = _build_objective(text, docs)

    _print_header("JARVIS - INVESTIGATION", emitter.run_id, provider.model_id, text, docs)
    _print_documents(docs)

    documents, page_starts = _load_documents(docs)
    printed: set[Stage] = set()

    async def on_stage(stage: Stage, result: MissionResult) -> None:
        """Print each stage as the run reaches it.

        Fires when a stage *begins*, so what is available is what the previous stage produced -
        which is why intent is printed at PLANNING and the plan at EXECUTING.
        """
        if stage in printed:
            return
        printed.add(stage)

        if stage is Stage.PLANNING and result.intent is not None:
            print("\n[1/4] understanding the objective ...")
            print(f"      goal: {result.intent.goal}")
            print(f"      {len(result.intent.required_operations)} operation(s) required")
            print("\n[2/4] planning ...")

        elif stage is Stage.EXECUTING and result.plan is not None:
            _print_plan(result.plan)
            await _print_routing(result.plan, emitter)
            print()
            print(RULE)
            print(f"[3/4] EXECUTING  ({len(documents)} document(s) loaded)")
            print(RULE)

        elif stage is Stage.REASONING:
            print(f"\n[4/4] reasoning over {len(result.observations)} observation(s) ...")

    result = await run_mission(
        objective=objective,
        documents=documents,
        provider=provider,
        emitter=emitter,
        page_starts=page_starts,
        on_stage=on_stage,
    )

    if result.status is MissionStatus.CLARIFICATION_NEEDED:
        print("\nCLARIFICATION NEEDED")
        print(f"  {result.error_message}")
        print("  (planning stops here - an ambiguous objective must not produce a plan)")
        _print_trace(sink, emitter.run_id)
        return 0

    if result.error_code == "PLAN_INVALID":
        print("\nPLAN_INVALID - the run fails cleanly rather than executing a bad plan")
        print(f"  {result.error_message}")
        _print_trace(sink, emitter.run_id)
        return 1

    if result.status is MissionStatus.FAILED:
        print(f"\nRUN FAILED - {result.error_code}")
        print(f"  {result.error_message}")
        _print_trace(sink, emitter.run_id)
        return 1

    # After the run, not during it: the replanning loop executes its inserted tasks *inside* the
    # loop, so a table printed when reasoning began would show the planned graph and miss exactly
    # the tasks worth pointing at.
    _print_execution(result)
    _print_findings(result)
    _print_gaps(result)

    if result.report is not None:
        print()
        print(to_text(result.report))
        if report_path:
            print()
            print(f"report written to {_write_report(report_path, to_markdown(result.report))}")

    _print_validation(result)
    _print_llm_stats(sink)
    print(RULE)
    print()
    return 0


def _print_plan(plan: Plan) -> None:
    """The task graph, and which tasks can run at the same time.

    The waves are the point: two tasks with no dependency between them have no edge, and that
    absence is what makes them concurrent. The parallelism is a property of the plan.
    """
    print()
    print(RULE)
    print("TASK GRAPH")
    print(RULE)
    for task in plan.tasks:
        deps = ", ".join(task.depends_on) if task.depends_on else "-"
        print(f"  {task.task_id}  {task.task_type.value:<24} depends on: {deps}")

    levels = execution_levels(plan)
    print(f"\nexecution waves ({len(levels)}):")
    for index, level in enumerate(levels):
        parallel = "   <- these run in parallel" if len(level) > 1 else ""
        print(f"  wave {index}: {', '.join(level)}{parallel}")


def _print_execution(result: MissionResult) -> None:
    """What every task did, and what evidence came back - the run's final state.

    A task inserted by the replanning loop is marked. `result.plan` carries the executed graph, so
    inserted tasks appear here - they did not when the plan was the planner's original output, and
    the adaptive behaviour was invisible as a result.
    """
    if result.plan is None:
        return

    print()
    print(RULE)
    print(f"EXECUTION  ({len(result.plan.tasks)} task(s))")
    print(RULE)

    for task in result.plan.tasks:
        tool = task.selection.tool_name if task.selection else "-"
        inserted = "  [INSERTED BY REPLAN]" if task.created_by_revision > 0 else ""
        note = ""
        if task.result and task.result.ok:
            note = next((o.content for o in result.observations if o.task_id == task.task_id), "")
        elif task.result:
            note = task.result.error_message[:60]
        print(f"  {task.task_id}  {task.status.value:<10} {tool:<20} {note}{inserted}")

    sources = sorted({s for o in result.observations for s in o.sources})
    completed = sum(1 for t in result.plan.tasks if t.status is TaskStatus.COMPLETED)
    print()
    print(f"tasks completed : {completed}/{len(result.plan.tasks)}")
    print(f"observations    : {len(result.observations)}")
    print(f"evidence found  : {len(sources)} located passage(s)")
    for source in sources[:8]:
        print(f"  - {source}")
    if len(sources) > 8:
        print(f"  ... and {len(sources) - 8} more")


def _print_findings(result: MissionResult) -> None:
    """Findings with their evidence and verification state.

    An unsupported claim is printed, not hidden, and an unresolvable citation is shown as such -
    dropping either would leave a report that looks better than the run was.
    """
    print()
    print(RULE)
    print(f"FINDINGS  ({len(result.findings)})")
    print(RULE)

    if not result.findings:
        print("  none - on an objective with nothing to find, this is the correct answer")
        return

    for finding in result.findings:
        status = finding.verification.status.value if finding.verification else "UNVERIFIED"
        degraded = ""
        if finding.verification and finding.verification.degraded:
            degraded = " (degraded check)"
        print()
        print(f"  [{finding.classification.value:<10}] {status}{degraded}")
        print(f"  confidence {finding.confidence.value:.2f}  {finding.claim}")
        for ref in finding.evidence:
            print(f"    - {ref.locator.as_ref():<32} {ref.resolution.value}")


def _print_gaps(result: MissionResult) -> None:
    if not result.gaps:
        return
    closed = sum(1 for g in result.gaps if g.resolved)
    print()
    print(f"evidence gaps   : {len(result.gaps)} detected, {closed} closed")
    for gap in result.gaps[:6]:
        mark = "closed" if gap.resolved else "open"
        print(f"  - [{mark:<6}] {gap.gap_type.value}: {gap.missing}")
    reason = result.termination_reason.value if result.termination_reason else "-"
    print(f"termination     : {reason}")
    print(f"replan rounds   : {result.replan_iterations}")


def _print_validation(result: MissionResult) -> None:
    validation = result.plan.validation if result.plan else None
    if validation is None:
        return
    print()
    print(f"validation      : {'PASSED' if validation.valid else 'FAILED'}")
    print(f"clean           : {validation.clean}  (no repairs, no re-prompts)")
    print(f"re-prompts      : {validation.reprompt_count}")
    if validation.repairs:
        print("repairs applied :")
        for applied in validation.repairs:
            print(f"  - {applied.action.value}: {applied.detail}")


async def _print_routing(plan: Plan, emitter: RunEventEmitter) -> None:
    """Show which tool serves each task, and how that was decided.

    The mode column is the point: DETERMINISTIC means the capability filter left exactly one
    candidate and no model was consulted. That is what makes tool-selection accuracy a
    property of the system rather than of the model.
    """
    registry = build_default_registry()
    router = ToolRouter(registry, get_provider())

    print()
    print(RULE)
    print(f"TOOL ROUTING  ({registry.count} tools registered)")
    print(RULE)

    modes: dict[str, int] = {}
    for task in plan.tasks:
        try:
            selection = await router.route(task, emit=emitter)
        except NoCapableToolError:
            print(f"  {task.task_id}  {'(no capable tool)':<22} SKIPPED - recorded, not dropped")
            modes["SKIPPED"] = modes.get("SKIPPED", 0) + 1
            continue
        modes[selection.mode.value] = modes.get(selection.mode.value, 0) + 1
        print(f"  {task.task_id}  {selection.tool_name:<22} {selection.mode.value}")

    summary = ", ".join(f"{count} {mode.lower()}" for mode, count in sorted(modes.items()))
    print(f"\nselection modes : {summary}")


def _write_report(report_path: str, markdown: str) -> Path:
    """Write the report. Synchronous on purpose: the run is over, nothing is waiting."""
    path = Path(report_path)
    path.write_text(markdown, encoding="utf-8")
    return path.resolve()


def _print_llm_stats(sink: MemoryEventSink) -> None:
    calls = sink.of_type(EventType.LLM_CALL_COMPLETED)
    if not calls:
        return
    repairs = sum(1 for c in calls if c.payload.get("repair_attempt", 0) > 0)
    latency = sum(int(c.payload.get("latency_ms", 0)) for c in calls)
    print()
    print(f"model calls     : {len(calls)}")
    print(f"repair attempts : {repairs}")
    print(f"total latency   : {latency} ms")


# How far a metric may move from the last report before the run is called a regression.
# Each one is wider than this suite's run-to-run noise: a local model is not
# deterministic, so a tolerance tighter than the jitter reports a regression every run
# and teaches everyone to ignore the check.
_TOLERANCES = {
    "intent_accuracy": 0.05,
    "plan_validity": 0.05,
    "dependency_correctness": 0.05,
    "tool_selection_accuracy": 0.05,
    "evidence_coverage": 0.03,
    "verification_success": 0.05,
    "replanning_success": 0.08,
    "unsupported_claim_rate": 0.02,
    "task_efficiency": 0.20,
    "latency_s": 30.0,
}


async def run_eval(suite: str, *, write: bool = True) -> int:
    """Run the evaluation suite and report measured metrics.

    Every number printed here is computed by a scorer from a real run. None is hard-coded,
    which is the whole point of the harness.
    """
    print()
    print(RULE)
    print(f"JARVIS AGENT EVALUATION  (suite: {suite})")
    print(RULE)

    report = await run_suite(suite)

    if not report.scenarios:
        print("no scenarios matched this suite")
        return 1

    print()
    print(f"model        : {report.model}")
    print(f"config       : {report.config_hash}")
    print(f"prompts      : {report.prompt_versions or '(none loaded)'}")
    print(f"scenarios    : {len(report.scenarios)}")

    print()
    print("PER SCENARIO")
    print("-" * 78)
    for scenario in report.scenarios:
        state = "ok" if scenario.ok else f"FAILED - {scenario.error[:40]}"
        print(
            f"  {scenario.scenario_id:<28} findings={scenario.findings:<3} "
            f"gaps={scenario.gaps_closed}/{scenario.gaps:<3} {state}"
        )

    print()
    print("AGGREGATE")
    print("-" * 78)
    for name, value in report.aggregate.as_dict().items():
        marker = "  (lower is better)" if name in LOWER_IS_BETTER else ""
        print(f"  {name:<28} {value:7.3f}{marker}")

    failures = report.build_failures()
    print()
    if failures:
        print("THRESHOLDS: FAILED")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("THRESHOLDS: passed")

    baseline = load_latest(reports_dir(), suite)
    if baseline is not None:
        result = compare(baseline, report, _TOLERANCES)
        print()
        if not result.comparable:
            print(f"REGRESSION CHECK: skipped - {result.reason}")
        elif result.regressions:
            print("REGRESSION CHECK: FAILED")
            for delta in result.regressions:
                print(
                    f"  - {delta.metric}: {delta.baseline:.3f} -> {delta.current:.3f} "
                    f"(tolerance {delta.tolerance:.2f})"
                )
        else:
            print("REGRESSION CHECK: passed")
            for delta in result.unexplained_improvements:
                print(
                    f"  ! {delta.metric} improved beyond tolerance "
                    f"({delta.baseline:.3f} -> {delta.current:.3f}); "
                    "check the measurement before celebrating"
                )

    if write:
        _, md_path = write_report(report, reports_dir())
        print()
        print(f"report written to {md_path}")

    print(RULE)
    print()
    return 1 if failures else 0


async def run_health() -> int:
    provider = get_provider()
    ok = await provider.health()
    print(f"provider : {provider.model_id}")
    print(f"status   : {'OK' if ok else 'UNREACHABLE'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    configure_logging()

    parser = argparse.ArgumentParser(prog="app.cli", description="JARVIS agent runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    intent_cmd = sub.add_parser("intent", help="analyse an objective")
    intent_cmd.add_argument("objective", help="what to investigate, in plain language")
    intent_cmd.add_argument("--docs", nargs="*", default=[], help="document filenames")

    plan_cmd = sub.add_parser("investigate", help="objective -> intent -> task graph")
    plan_cmd.add_argument("objective", help="what to investigate, in plain language")
    plan_cmd.add_argument("--docs", nargs="*", default=[], help="document filenames")
    plan_cmd.add_argument(
        "--report", default="", help="write the final report to this Markdown file"
    )

    eval_cmd = sub.add_parser("eval", help="run the agent evaluation suite")
    eval_cmd.add_argument("--suite", default="all", help="core | negative | all")
    eval_cmd.add_argument("--no-write", action="store_true", help="do not write a report file")

    sub.add_parser("health", help="check the configured provider")

    args = parser.parse_args(argv)

    if args.command == "intent":
        return asyncio.run(run_intent(args.objective, args.docs))
    if args.command == "eval":
        return asyncio.run(run_eval(args.suite, write=not args.no_write))
    if args.command == "investigate":
        return asyncio.run(run_investigate(args.objective, args.docs, args.report))
    return asyncio.run(run_health())


if __name__ == "__main__":
    sys.exit(main())
