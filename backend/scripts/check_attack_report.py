"""Check the committed ATT&CK mapping report against a fresh run (Phase 53).

    python scripts/check_attack_report.py

Deterministic and model-free, so CI re-runs it, and fails when no report is committed, when the
committed one no longer describes the code (a different dataset, catalogue, or any fixture's mapping
changed), or when a technique is mapped that the ground truth does not hold.
"""

from __future__ import annotations

import sys

from app.evaluation.attack import AttackReport, attack_dir, run_attack_benchmark


def main() -> int:
    paths = sorted((attack_dir() / "reports").glob("*.json"))
    if not paths:
        print("no ATT&CK report committed: run `python -m app.cli eval-attack` and commit it")
        return 1
    committed = AttackReport.model_validate_json(paths[-1].read_text(encoding="utf-8"))
    fresh = run_attack_benchmark()
    failures: list[str] = []
    if committed.dataset_hash != fresh.dataset_hash:
        failures.append(f"dataset changed: {committed.dataset_hash} -> {fresh.dataset_hash}")
    if committed.attack_version != fresh.attack_version:
        failures.append(f"catalogue changed: {committed.attack_version} -> {fresh.attack_version}")
    before = {c.fixture: c.mapped for c in committed.cases}
    changed = [c.fixture for c in fresh.cases if before.get(c.fixture) != c.mapped]
    if changed:
        failures.append(f"mapping changed for: {', '.join(changed)}")
    wrong = [
        f"{c.fixture}: {', '.join(c.false_positives)}" for c in fresh.cases if c.false_positives
    ]
    if wrong:
        failures.append(
            f"techniques mapped that the ground truth does not hold: {'; '.join(wrong)}"
        )
    print(f"ATT&CK report: {paths[-1].name}")
    print(
        f"precision {fresh.technique_precision:.3f}, recall {fresh.technique_recall:.3f}, "
        f"held-out recall {fresh.held_out_recall:.3f}"
    )
    if failures:
        print("FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("the committed ATT&CK report is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
