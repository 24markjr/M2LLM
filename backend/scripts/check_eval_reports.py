"""Validate the committed evaluation reports, and enforce the thresholds they recorded.

    python scripts/check_eval_reports.py

**What this is not.** It does not run the agent. That needs a local model, and a CI runner has
none. Pretending otherwise would be the worst possible outcome here: a green tick that a reader
takes as evidence the agent was measured, when nothing was measured at all.

What it does check is still worth a gate:

- every report parses as an `EvalReport`, so a hand-edited or truncated one fails
- every report carries its stamp (model, prompt versions, config hash), because a report without
  one is not comparable to anything and cannot be a baseline
- the thresholds are enforced on the **newest report per suite**, which is the baseline: a
  current result with a confabulation, a positive-case blind spot, or an unsupported-claim rate
  over the ceiling fails the build

Thresholds are deliberately *not* enforced on older reports. A report recording a defect that was
subsequently fixed is exactly the evidence worth keeping, and a gate that failed on it would
pressure someone into deleting the record to go green. History has to parse and be stamped;
only the baseline has to pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.evaluation.report import EvalReport
from app.evaluation.runner import reports_dir


def main() -> int:
    directory = reports_dir()
    if not directory.is_dir():
        print(f"no reports directory at {directory} - nothing to check")
        return 0

    paths = sorted(directory.glob("*.json"))
    if not paths:
        print("no committed evaluation reports yet - nothing to check")
        return 0

    failures: list[str] = []
    checked = 0
    # The newest report for each suite is that suite's baseline, and the only one whose
    # thresholds gate the build. Filenames are `<timestamp>-<model>-<suite>.json`, so sorted
    # order is chronological and the last per suite wins.
    baselines: dict[str, Path] = {}

    for path in paths:
        try:
            report = EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append(f"{path.name}: does not parse as a report ({type(exc).__name__})")
            continue

        checked += 1

        # A report without a stamp cannot be compared to another, so it cannot be a baseline.
        if not report.model:
            failures.append(f"{path.name}: no model recorded")
        if not report.config_hash:
            failures.append(f"{path.name}: no config hash recorded")
        if not report.scenarios:
            failures.append(f"{path.name}: no scenarios - an empty report is not a result")

        baselines[report.suite] = path

    for suite, path in sorted(baselines.items()):
        report = EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
        for failure in report.build_failures():
            failures.append(f"[{suite} baseline: {path.name}] {failure}")

    print(f"checked {checked} report(s) in {directory}")
    print(f"baselines gated: {', '.join(f'{s}={p.name}' for s, p in sorted(baselines.items()))}")

    if failures:
        print("\nFAILED")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nNote: these are the thresholds the reports themselves recorded. The metrics are "
            "produced locally with a real model; this check only enforces what was committed."
        )
        return 1

    print("all committed reports are well-formed and within their recorded thresholds")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
