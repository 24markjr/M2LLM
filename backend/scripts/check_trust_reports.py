"""Check the committed trust and security report against a fresh run (Phase 34).

    python scripts/check_trust_reports.py

Member 4's verifier benchmark and the prompt-injection suite are deterministic and need no model,
so unlike the agent evaluation they **can** be re-run in CI. This does, and fails when:

- no trust report is committed (`python -m app.cli eval-trust` writes one)
- the newest committed report does not match what the code produces now: a different dataset, a
  different verifier or thresholds, or any case whose verdict changed. A report that no longer
  describes the code is a number the documentation should not quote.
- any security case fails: an attack the scanner should flag and does not, a clean text it flags,
  or a category it misnames. The documented result is every case correct, so that is the gate.

Latency is not compared: it measures the machine, not the code.
"""

from __future__ import annotations

import sys

from app.evaluation.trust import TrustReport, run_trust_benchmark, trust_dir


def main() -> int:
    paths = sorted((trust_dir() / "reports").glob("*.json"))
    if not paths:
        print("no trust report committed: run `python -m app.cli eval-trust` and commit it")
        return 1

    committed = TrustReport.model_validate_json(paths[-1].read_text(encoding="utf-8"))
    fresh = run_trust_benchmark()
    failures: list[str] = []

    if committed.dataset_hash != fresh.dataset_hash:
        failures.append(
            f"dataset changed: committed {committed.dataset_hash}, now {fresh.dataset_hash}"
        )
    if committed.verifier != fresh.verifier or committed.thresholds != fresh.thresholds:
        failures.append("the verifier or its thresholds changed since the report was written")

    before = {r.case_id: r.actual for r in committed.results}
    changed = [r.case_id for r in fresh.results if before.get(r.case_id) != r.actual]
    if changed:
        failures.append(
            f"{len(changed)} trust case(s) now give a different verdict: {', '.join(changed[:10])}"
        )

    security = fresh.security
    if security is None or committed.security is None:
        failures.append("the report carries no security results")
    else:
        flags_before = {r.id: r.flagged for r in committed.security.results}
        flags_changed = [r.id for r in security.results if flags_before.get(r.id) != r.flagged]
        if flags_changed:
            failures.append(f"security case(s) changed: {', '.join(flags_changed)}")
        for case in security.failures:
            failures.append(
                f"security case {case.id} fails: expected flag={case.expected_flag}, "
                f"got {case.flagged} ({', '.join(case.categories) or 'no category'})"
            )

    print(f"checked {paths[-1].name} against a fresh run")
    print(
        f"  trust     {fresh.correct}/{fresh.cases} correct, hallucination_rate "
        f"{fresh.hallucination_rate:.3f}"
    )
    if security is not None:
        correct = security.cases - len(security.failures)
        print(f"  security  {correct}/{security.cases} correct")
    if failures:
        print("FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
