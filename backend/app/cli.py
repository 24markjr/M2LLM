"""JARVIS command line — the demonstration entry point.

    python -m app.cli intent "Investigate these reports for timeline inconsistencies."
    python -m app.cli intent "..." --docs project_report.pdf budget.csv
    python -m app.cli health

Output is ASCII only: the Windows console defaults to cp1252 (BUG-001).

What this shows is deliberately *operational*: the objective going in, the timeline of what
the agent did, and the structured intent coming out. It never shows model deliberation
(invariant #3) - what you see is what the system decided, not what it was thinking.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.core.logging import configure_logging
from app.intelligence.intent.engine import IntentEngine, derive_operations
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


async def run_intent(text: str, docs: list[str]) -> int:
    provider = get_provider()

    bus_sink = MemoryEventSink()
    bus = EventBus([bus_sink])
    run_id = new_run_id()
    emitter = RunEventEmitter(bus, run_id)

    objective = _build_objective(text, docs)

    print(f"\n{RULE}")
    print("JARVIS - INTENT ANALYSIS")
    print(RULE)
    print(f"run       : {run_id}")
    print(f"model     : {provider.model_id}")
    print(f"objective : {text}")
    print(f"documents : {', '.join(docs) if docs else '(none)'}")

    # The deterministic pre-pass, shown separately so the split between what the system
    # derives structurally and what the model contributes is visible.
    heuristic = derive_operations(objective)
    print(f"\npre-pass  : {len(heuristic)} operation(s) derived without the model")
    for op in sorted(heuristic, key=lambda o: o.value):
        print(f"            - {op.value}")

    await emitter.emit(EventType.RUN_STARTED, payload={"objective": text})

    print("\nanalysing ...")
    engine = IntentEngine(provider)
    intent = await engine.analyze(objective, emit=emitter)
    await emitter.emit(EventType.RUN_COMPLETED)

    print(f"\n{RULE}")
    print("EXECUTION TRACE")
    print(RULE)
    for event in bus_sink.for_run(run_id):
        print(f"  {event.describe()}")

    print(f"\n{RULE}")
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

    llm_calls = bus_sink.of_type(EventType.LLM_CALL_COMPLETED)
    if llm_calls:
        payload = llm_calls[-1].payload
        print(f"\nmodel calls     : {len(llm_calls)}")
        print(f"repair attempts : {payload.get('repair_attempt', 0)}")
        print(f"latency         : {payload.get('latency_ms', 0)} ms")

    print(f"{RULE}\n")
    return 0


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

    sub.add_parser("health", help="check the configured provider")

    args = parser.parse_args(argv)

    if args.command == "intent":
        return asyncio.run(run_intent(args.objective, args.docs))
    return asyncio.run(run_health())


if __name__ == "__main__":
    sys.exit(main())
