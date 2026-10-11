"""Check the committed challenge report against a fresh run (Phase 48).

    python scripts/check_challenge_report.py

The challenge benchmark is deterministic and needs no model, so CI re-runs it, and fails when:

- no challenge report is committed (`python -m app.cli eval-challenge` writes one);
- the newest committed report does not describe the code now: a different dataset, or any case
  whose outcome changed - a figure the documentation quotes would then be stale;
- a true finding is overturned (a false alarm). A missed false finding is reported, not gated: the
  known miss is part of what the benchmark documents.
"""

from __future__ import annotations

import asyncio
import sys

from app.evaluation.challenge import ChallengeReport, challenge_dir, run_challenge_benchmark


def main() -> int:
    paths = sorted((challenge_dir() / "reports").glob("*.json"))
    if not paths:
        print("no challenge report committed: run `python -m app.cli eval-challenge` and commit it")
        return 1
    committed = ChallengeReport.model_validate_json(paths[-1].read_text(encoding="utf-8"))
    fresh = asyncio.run(run_challenge_benchmark())
    failures: list[str] = []
    if committed.dataset_hash != fresh.dataset_hash:
        failures.append(
            f"dataset changed: committed {committed.dataset_hash}, now {fresh.dataset_hash}"
        )
    before = {r.case_id: r.outcome for r in committed.results}
    changed = [r.case_id for r in fresh.results if before.get(r.case_id) != r.outcome]
    if changed:
        failures.append(f"case(s) now give a different outcome: {', '.join(changed)}")
    alarms = [r.case_id for r in fresh.results if r.false_alarm]
    if alarms:
        failures.append(f"true finding(s) overturned: {', '.join(alarms)}")

    print(f"challenge report: {paths[-1].name}")
    print(
        f"catch rate {fresh.challenge_catch_rate:.3f}, "
        f"false alarm rate {fresh.challenge_false_alarm_rate:.3f}"
    )
    if failures:
        print("FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("the committed challenge report is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
