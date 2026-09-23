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

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.core.logging import configure_logging
from app.intelligence.intent.engine import IntentEngine, derive_operations
from app.intelligence.planner.engine import PlanInvalidError, Planner, execution_levels
from app.llm import get_provider
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.objective import AttachedDocument, DocumentKind, Objective, ObjectiveScope

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


async def run_investigate(text: str, docs: list[str]) -> int:
    """Objective -> intent -> validated task graph. The end-to-end demo."""
    provider = get_provider()
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    objective = _build_objective(text, docs)

    _print_header("JARVIS - INVESTIGATION PLANNING", emitter.run_id, provider.model_id, text, docs)

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

    sub.add_parser("health", help="check the configured provider")

    args = parser.parse_args(argv)

    if args.command == "intent":
        return asyncio.run(run_intent(args.objective, args.docs))
    if args.command == "investigate":
        return asyncio.run(run_investigate(args.objective, args.docs))
    return asyncio.run(run_health())


if __name__ == "__main__":
    sys.exit(main())
