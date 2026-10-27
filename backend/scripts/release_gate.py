"""The release gate (v4 Phase 9): red blocks a release.

Reads the newest benchmark report in `.agent/evals/benchmark/reports/` and checks it against
`.agent/config/release_gate.yaml`: the floors block, the targets are reported. Deterministic - it
reads a committed report, it runs no model - so CI can run it on every push, and `deploy/deploy.sh`
runs it before building anything.

    python scripts/release_gate.py            # exit 0 green, 1 red
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / ".agent" / "evals" / "benchmark" / "reports"
CONFIG = ROOT / ".agent" / "config" / "release_gate.yaml"


def main() -> int:
    gate = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["benchmark"]
    floor, target = gate["floor"], gate["target"]
    reports = sorted(REPORTS.glob("*-benchmark.json"))
    if not reports:
        print("RED  no benchmark report: run python -m app.evaluation.benchmark")
        return 1
    path = reports[-1]
    report = json.loads(path.read_text(encoding="utf-8"))
    systems = {s["system"]: s for s in report["systems"]}
    jarvis, plain = systems.get("jarvis"), systems.get("plain")
    print(f"Release gate on {path.name} (model {report.get('model', '?')})")
    if jarvis is None:
        print("RED  the report has no JARVIS run")
        return 1

    age = (datetime.now(UTC) - datetime.fromisoformat(report["generated_at"])).days
    checks = [
        (
            "correct",
            (jarvis["correct"] or 0) >= floor["correct"],
            jarvis["correct"],
            f">= {floor['correct']}",
        ),
        (
            "factscore",
            (jarvis["factscore"] or 0) >= floor["factscore"],
            jarvis["factscore"],
            f">= {floor['factscore']}",
        ),
        (
            "citation precision",
            (jarvis["citation_precision"] or 0) >= floor["citation_precision"],
            jarvis["citation_precision"],
            f">= {floor['citation_precision']}",
        ),
        (
            "invented values",
            jarvis["invented"] <= floor["invented_max"],
            jarvis["invented"],
            f"<= {floor['invented_max']}",
        ),
        (
            "false alarms",
            jarvis["false_alarms"] <= floor["false_alarms_max"],
            jarvis["false_alarms"],
            f"<= {floor['false_alarms_max']}",
        ),
        (
            "errors",
            jarvis["errors"] <= floor["errors_max"],
            jarvis["errors"],
            f"<= {floor['errors_max']}",
        ),
        (
            "mean latency (s)",
            jarvis["mean_latency_s"] <= floor["mean_latency_s_max"],
            jarvis["mean_latency_s"],
            f"<= {floor['mean_latency_s_max']}",
        ),
        (
            "scenarios",
            jarvis["scenarios"] >= floor["scenarios_min"],
            jarvis["scenarios"],
            f">= {floor['scenarios_min']}",
        ),
        ("report age (days)", age <= gate["max_age_days"], age, f"<= {gate['max_age_days']}"),
    ]
    red = False
    for name, ok, value, rule in checks:
        print(f"{'GREEN' if ok else 'RED  '} {name:20} {value!s:>8}  {rule}")
        red |= not ok

    print("Targets (reported, not blocking):")
    if plain is not None:
        gap = round((jarvis["correct"] or 0) - (plain["correct"] or 0), 3)
        state = "met " if gap >= target["correct_vs_plain"] else "not "
        print(f"  {state} correct vs plain model  {gap:+}")
    met = (jarvis["citation_precision"] or 0) >= target["citation_precision"]
    print(f"  {'met ' if met else 'not '} citation precision >= {target['citation_precision']}")

    print("RED - the release is blocked" if red else "GREEN - the release may go")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
