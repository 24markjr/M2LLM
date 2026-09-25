"""Every metric quoted in prose must match the committed baseline report.

    python scripts/check_documented_metrics.py

Phase 24's acceptance criterion is that no metric shown anywhere is hard-coded. The README and the
contribution statement both quote figures, and a figure typed into markdown drifts the moment the
suite is re-run - at which point the documentation is confidently wrong, which is worse than having
no figure at all.

This makes the criterion enforceable rather than aspirational: it pulls every ``metric`` mentioned
alongside a number out of the documents and compares it against the baseline report. It does not
check that the number is *good*, only that it is *true*.

**Historical figures.** A document legitimately quotes past numbers - what the harness measured
before a fix - and those must not be rewritten to match today's baseline, because then the record
of the improvement disappears. Wrap them:

    <!-- historical -->
    ... a table of what was measured previously ...
    <!-- /historical -->

Declared rather than inferred: the marker is a claim that the number is deliberately not current,
and an undeclared stale figure still fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from app.evaluation.metrics import MetricSet
from app.evaluation.report import EvalReport
from app.evaluation.runner import reports_dir

ROOT = Path(__file__).resolve().parents[2]

# Documents that quote figures. A new one belongs here the moment it does.
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "docs" / "contribution.md",
]

# `metric_name` followed by a number, with optional table pipe and bold markers between them.
# Covers both `| \`plan_validity\` | 0.333 |` and "\`plan_validity\` **0.333**".
PATTERN = re.compile(
    r"`(?P<metric>[a-z_]+)`\s*\|?\s*\*{0,2}(?P<value>\d+\.\d+)\*{0,2}",
)

# How far a quoted figure may differ from the report. Tight: this is a transcription check, not a
# tolerance for drift.
EPSILON = 0.0005

KNOWN_METRICS = set(MetricSet.model_fields)


def baseline(suite: str = "all") -> tuple[EvalReport, Path] | None:
    """The newest report for a suite. Filenames sort chronologically."""
    directory = reports_dir()
    if not directory.is_dir():
        return None
    candidates = sorted(p for p in directory.glob("*.json") if p.stem.endswith(f"-{suite}"))
    if not candidates:
        return None
    path = candidates[-1]
    return EvalReport.model_validate_json(path.read_text(encoding="utf-8")), path


def main() -> int:
    found = baseline()
    if found is None:
        print("no baseline report for suite 'all' - nothing to check against")
        return 0

    report, path = found
    aggregate = report.aggregate.as_dict()
    print(f"baseline: {path.name} ({report.model})")

    failures: list[str] = []
    checked = 0

    for document in DOCUMENTS:
        if not document.is_file():
            failures.append(f"{document.name}: listed for checking but missing")
            continue

        historical = False
        for line_number, line in enumerate(
            document.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped == "<!-- historical -->":
                historical = True
                continue
            if stripped == "<!-- /historical -->":
                historical = False
                continue
            if historical:
                continue

            for match in PATTERN.finditer(line):
                metric = match.group("metric")
                if metric not in KNOWN_METRICS:
                    continue

                quoted = float(match.group("value"))
                actual = float(aggregate[metric])
                checked += 1

                if abs(quoted - actual) > EPSILON:
                    failures.append(
                        f"{document.name}:{line_number}: {metric} is quoted as {quoted:.3f} "
                        f"but the baseline reports {actual:.3f}"
                    )

    print(f"checked {checked} quoted figure(s) across {len(DOCUMENTS)} document(s)")

    if failures:
        print("\nFAILED - the documentation quotes numbers the baseline does not support")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nEither re-run `python -m app.cli eval --suite all` and commit the report, or "
            "correct the figure. A stale number is worse than no number."
        )
        return 1

    if checked == 0:
        # Not a pass. If the pattern stops matching - a table gets reformatted, say - this check
        # would silently verify nothing and keep reporting success.
        print("\nFAILED - no figures matched, so this check verified nothing")
        return 1

    print("every quoted figure matches the baseline")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
