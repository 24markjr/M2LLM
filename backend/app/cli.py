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
from app.integrations.verification import build_verification_provider
from app.intelligence.execution.engine import ExecutionEngine
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.intent.engine import IntentEngine, derive_operations
from app.intelligence.planner.engine import PlanInvalidError, Planner, execution_levels
from app.intelligence.reasoning.engine import ReasoningEngine
from app.intelligence.replanning.controller import ReplanningController, ReplanResult
from app.intelligence.router.engine import NoCapableToolError, ToolRouter
from app.intelligence.synthesis.engine import SynthesisEngine
from app.intelligence.synthesis.renderers import to_markdown, to_text
from app.llm import get_provider
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.execution import Observation
from app.schemas.objective import AttachedDocument, DocumentKind, Objective, ObjectiveScope
from app.schemas.plan import Plan
from app.schemas.result import ExecutionSummary
from app.tools.base import ToolContext, ToolRegistry, build_default_registry
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
    """Objective -> intent -> validated task graph. The end-to-end demo."""
    provider = get_provider()
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    objective = _build_objective(text, docs)

    _print_header("JARVIS - INVESTIGATION PLANNING", emitter.run_id, provider.model_id, text, docs)

    _print_documents(docs)

    await emitter.emit(EventType.RUN_STARTED, payload={"objective": text})

    print("\n[1/2] understanding the objective ...")
    intent = await IntentEngine(provider).analyze(objective, emit=emitter)
    print(f"      goal: {intent.goal}")
    print(f"      {len(intent.required_operations)} operation(s) required")

    if intent.clarification_needed:
        print("\nCLARIFICATION NEEDED")
        print(f"  {intent.clarification_question}")
        print("  (planning stops here - an ambiguous objective must not produce a plan)")
        await emitter.emit(EventType.RUN_COMPLETED)
        _print_trace(sink, emitter.run_id)
        return 0

    print("\n[2/2] planning ...")
    try:
        plan = await Planner(provider).create_plan(intent, objective, emit=emitter)
    except PlanInvalidError as exc:
        print("\nPLAN_INVALID - the run fails cleanly rather than executing a bad plan")
        for violation in exc.result.violations:
            print(f"  - [{violation.code.value}] {violation.message}")
        await emitter.emit(EventType.RUN_FAILED)
        _print_trace(sink, emitter.run_id)
        return 1

    await emitter.emit(EventType.RUN_COMPLETED)
    _print_trace(sink, emitter.run_id)

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

    await _print_routing(plan, emitter)

    observations, graph, registry = await _execute(plan, docs, emitter, sink)
    await _investigate(objective, observations, graph, registry, docs, emitter, report_path)

    validation = plan.validation
    if validation:
        print()
        print(f"validation      : {'PASSED' if validation.valid else 'FAILED'}")
        print(f"clean           : {validation.clean}  (no repairs, no re-prompts)")
        print(f"re-prompts      : {validation.reprompt_count}")
        if validation.repairs:
            print("repairs applied :")
            for applied in validation.repairs:
                print(f"  - {applied.action.value}: {applied.detail}")

    _print_llm_stats(sink)
    print(RULE)
    print()
    return 0


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


async def _execute(
    plan: Plan, docs: list[str], emitter: RunEventEmitter, sink: MemoryEventSink
) -> tuple[list[Observation], TaskGraph | None, ToolRegistry | None]:
    """Run the plan. This is where JARVIS stops planning and starts doing.

    Returns the graph and registry as well as the observations: the replanning loop
    edits the *same* graph, which is what makes an inserted task part of this run
    rather than a separate one."""
    documents, page_starts = _load_documents(docs)
    if not documents:
        print()
        print("(no fixture documents matched - skipping execution)")
        return [], None, None

    registry = build_default_registry()
    graph = TaskGraph.from_plan(plan)
    engine = ExecutionEngine(graph, registry, ToolRouter(registry), emit=emitter)
    ctx = ToolContext(
        run_id=emitter.run_id,
        document_ids=list(documents),
        documents=documents,
        page_starts=page_starts,
    )

    print()
    print(RULE)
    print(f"EXECUTION  ({len(documents)} document(s) loaded)")
    print(RULE)

    observations = await engine.run(ctx)

    for task in graph.tasks:
        tool = task.selection.tool_name if task.selection else "-"
        note = ""
        if task.result and task.result.ok:
            note = next((o.content for o in observations if o.task_id == task.task_id), "")
        elif task.result:
            note = task.result.error_message[:60]
        print(f"  {task.task_id}  {task.status.value:<10} {tool:<20} {note}")

    done, total = graph.progress()
    sources = sorted({s for o in observations for s in o.sources})
    print()
    print(f"tasks completed : {done}/{total}")
    print(f"observations    : {len(observations)}")
    print(f"tool calls      : {engine.budget.tool_calls_used}/{engine.budget.tool_calls_limit}")
    print(f"evidence found  : {len(sources)} located passage(s)")
    for source in sources[:8]:
        print(f"  - {source}")
    if len(sources) > 8:
        print(f"  ... and {len(sources) - 8} more")

    print()
    return observations, graph, registry


async def _investigate(
    objective: Objective,
    observations: list[Observation],
    graph: TaskGraph | None,
    registry: ToolRegistry | None,
    docs: list[str],
    emitter: RunEventEmitter,
    report_path: str = "",
) -> None:
    """Reason, verify, detect gaps, and replan until resolved or bounded out.

    This is the closed loop: everything before it is a pipeline. When verification
    rejects a finding and a gap names what is missing, a task is inserted into the graph
    that already ran and execution continues.
    """
    if not observations or graph is None or registry is None:
        return

    provider = get_provider()
    documents, page_starts = _load_documents(docs)

    print()
    print(RULE)
    print("REASONING, VERIFICATION AND ADAPTIVE REPLANNING")
    print(RULE)
    print(f"deriving findings from {len(observations)} observation(s) ...")

    controller = ReplanningController(
        graph=graph,
        registry=registry,
        router=ToolRouter(registry, provider),
        reasoner=ReasoningEngine(provider),
        verifier=build_verification_provider(provider),
        emit=emitter,
    )
    ctx = ToolContext(
        run_id=emitter.run_id,
        document_ids=list(documents),
        documents=documents,
        page_starts=page_starts,
    )
    result = await controller.run(objective, observations, ctx)

    if not result.findings:
        print()
        print("no findings could be supported by the evidence gathered")
        print("(an honest empty result - the system does not invent one to fill the gap)")
        print(f"terminated       : {result.termination_reason.value}")
        return

    scores = {s.gap_id: s for s in result.scores}

    for finding in result.findings:
        print()
        print(f"  {finding.finding_id}  [{finding.classification.value}] {finding.claim}")
        print(f"        confidence   : {finding.confidence.explain()}")

        if finding.verification is not None:
            issues = ", ".join(i.issue_type.value for i in finding.verification.issues)
            detail = f" - {issues}" if issues else ""
            degraded = "  (degraded to baseline)" if finding.verification.degraded else ""
            print(f"        verification : {finding.verification.status.value}{detail}{degraded}")

        for ref in finding.evidence:
            mark = "resolved  " if ref.is_resolved else "UNRESOLVED"
            note = "" if ref.is_resolved else f"  <- {ref.resolution_note}"
            print(f"        {mark} {ref.as_ref()}{note}")

        for gap in finding.gaps:
            print(f"        GAP          : {gap.missing}")
            print(f"                       ({gap.gap_type.value}, severity {gap.severity:.2f})")
            score = scores.get(gap.gap_id)
            if gap.resolved_by_task_id:
                scored = f"  score {score.explain()}" if score else ""
                state = "resolved" if gap.resolved else "pending"
                print(f"        ACTION       : {gap.resolved_by_task_id} [{state}]{scored}")

    verified = len(result.verified)
    resolved_gaps = sum(1 for g in result.gaps if g.resolved)

    print()
    print(f"findings          : {len(result.findings)}  ({verified} verified)")
    print(f"gaps detected     : {len(result.gaps)}  ({resolved_gaps} closed)")
    print(f"replan iterations : {result.iterations}")
    print(f"tasks added       : {sum(len(r.added_task_ids) for r in result.revisions)}")
    print(f"mean confidence   : {result.mean_confidence:.2f}")
    print(f"terminated        : {result.termination_reason.value}")

    if result.termination_reason.value == "DIMINISHING_RETURNS":
        print("  (the loop recognised another iteration was not worth the cost)")
    elif result.termination_reason.value == "MAX_ITERATIONS":
        print("  (the iteration ceiling was reached; unresolved gaps are reported as such)")

    await _report(objective, result, graph, documents, emitter, report_path)


async def _report(
    objective: Objective,
    result: ReplanResult,
    graph: TaskGraph,
    documents: dict[str, str],
    emitter: RunEventEmitter,
    report_path: str,
) -> None:
    """Assemble and show the final report.

    Every figure here is counted from the run rather than described by a model - the
    narrative is the only generated text in the document.
    """
    from app.schemas.task import TaskStatus

    _, total = graph.progress()
    execution = ExecutionSummary(
        tasks_planned=total,
        tasks_completed=len(graph.with_status(TaskStatus.COMPLETED)),
        tasks_failed=len(graph.with_status(TaskStatus.FAILED)),
        tasks_skipped=len(graph.with_status(TaskStatus.SKIPPED)),
        tool_calls=sum(1 for t in graph.tasks if t.result is not None),
        documents_processed=len(documents),
        replan_iterations=result.iterations,
        gaps_detected=len(result.gaps),
        gaps_resolved=sum(1 for g in result.gaps if g.resolved),
    )

    report = await SynthesisEngine(get_provider()).synthesize(
        run_id=emitter.run_id,
        objective=objective,
        findings=result.findings,
        gaps=result.gaps,
        observations=result.observations,
        execution=execution,
        termination=result.termination_reason,
        emit=emitter,
    )

    print()
    print(to_text(report))

    if report_path:
        print()
        print(f"report written to {_write_report(report_path, to_markdown(report))}")


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

    sub.add_parser("health", help="check the configured provider")

    args = parser.parse_args(argv)

    if args.command == "intent":
        return asyncio.run(run_intent(args.objective, args.docs))
    if args.command == "investigate":
        return asyncio.run(run_investigate(args.objective, args.docs, args.report))
    return asyncio.run(run_health())


if __name__ == "__main__":
    sys.exit(main())
