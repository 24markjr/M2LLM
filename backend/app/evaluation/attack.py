"""The ATT&CK mapping benchmark: technique precision and recall (Phase 53).

Four fixtures with techniques an analyst would assign, written as ground truth below. Three were
written beside the rules (PowerShell download cradle, PsExec lateral movement, benign
administration); one - `cyber_persistence_held_out.jsonl`: an RDP logon, a certutil download, a
scheduled task - was written after them, with the techniques it shows whether or not a rule covers
them. Precision is how many mapped techniques are right; recall, how many right ones were mapped.
Deterministic, no model; re-run in CI.

**What it shows.** The three fixtures written with the rules mostly measure that the rules do what
they say. The held-out fixture measures what they miss: rules cover what someone wrote a rule for,
and the honest number for anything else is its recall.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.core.config import get_settings
from app.cyber.analysis import analyse
from app.cyber.attack import get_catalogue
from app.schemas.common import JarvisModel, UnitFloat, utcnow
from app.tools.formats import parse

GROUND_TRUTH: dict[str, set[str]] = {
    "cyber_ws12_security.xml": {"T1059.001", "T1027", "T1105", "T1204.002", "T1071.001"},
    "cyber_lateral_movement.jsonl": {
        "T1078",
        "T1569.002",
        "T1021.002",
        "T1543.003",
        "T1033",
        "T1069.002",
        "T1218.011",
    },
    "cyber_admin_benign.log": set(),
    # Written after the rules: an RDP logon (T1078, T1021.001), a certutil download (T1105), a
    # scheduled task (T1053.005), PowerShell (T1059.001).
    "cyber_persistence_held_out.jsonl": {"T1078", "T1021.001", "T1105", "T1053.005", "T1059.001"},
}


class AttackCase(JarvisModel):
    fixture: str
    expected: list[str]
    mapped: list[str]
    true_positives: list[str]
    false_positives: list[str]
    missed: list[str]


class AttackReport(JarvisModel):
    generated_at: datetime = Field(default_factory=utcnow)
    attack_version: str
    dataset_hash: str
    technique_precision: UnitFloat
    technique_recall: UnitFloat
    held_out_recall: UnitFloat
    cases: list[AttackCase] = Field(default_factory=list)


def _fixtures() -> Path:
    return get_settings().agent_dir / "fixtures" / "documents"


def dataset_hash() -> str:
    digest = hashlib.sha256()
    for name in sorted(GROUND_TRUTH):
        digest.update(name.encode())
        digest.update((_fixtures() / name).read_bytes())
        digest.update(",".join(sorted(GROUND_TRUTH[name])).encode())
    return "sha256:" + digest.hexdigest()[:16]


def run_attack_benchmark() -> AttackReport:
    cases: list[AttackCase] = []
    for name, expected in GROUND_TRUTH.items():
        analysis = analyse({name: parse(_fixtures() / name).text})
        mapped = {m.technique_id for m in analysis.techniques}
        cases.append(
            AttackCase(
                fixture=name,
                expected=sorted(expected),
                mapped=sorted(mapped),
                true_positives=sorted(mapped & expected),
                false_positives=sorted(mapped - expected),
                missed=sorted(expected - mapped),
            )
        )
    tp = sum(len(c.true_positives) for c in cases)
    fp = sum(len(c.false_positives) for c in cases)
    fn = sum(len(c.missed) for c in cases)
    held = next(c for c in cases if c.fixture == "cyber_persistence_held_out.jsonl")
    catalogue = get_catalogue()
    return AttackReport(
        attack_version=f"ATT&CK v{catalogue.version}" if catalogue else "",
        dataset_hash=dataset_hash(),
        technique_precision=tp / (tp + fp) if tp + fp else 1.0,
        technique_recall=tp / (tp + fn) if tp + fn else 1.0,
        held_out_recall=len(held.true_positives) / len(held.expected) if held.expected else 1.0,
        cases=cases,
    )


def attack_dir() -> Path:
    return get_settings().agent_dir / "evals" / "attack"


def write_attack_report(report: AttackReport) -> tuple[Path, Path]:
    directory = attack_dir() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%S")
    json_path = directory / f"{stamp}-attack.json"
    md_path = directory / f"{stamp}-attack.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lines = [
        "# ATT&CK mapping benchmark",
        "",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M UTC}  ",
        f"**Catalogue:** {report.attack_version}  ",
        f"**Dataset:** `{report.dataset_hash}`",
        "",
        "Deterministic, no model. Computed by `app/evaluation/attack.py`.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| technique_precision | {report.technique_precision:.3f} |",
        f"| technique_recall | {report.technique_recall:.3f} |",
        f"| held_out_recall | {report.held_out_recall:.3f} |",
        "",
        "| Fixture | Mapped | Missed | Wrong |",
        "|---|---|---|---|",
    ]
    for c in report.cases:
        lines.append(
            f"| {c.fixture} | {', '.join(c.true_positives) or '-'} | "
            f"{', '.join(c.missed) or '-'} | {', '.join(c.false_positives) or '-'} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
