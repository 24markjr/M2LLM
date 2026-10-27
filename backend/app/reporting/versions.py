"""Report versions (v4 Phase 5): every export is a numbered version, signed and tied to a snapshot.

A report changes as its case does - a finding reviewed, a challenge recorded, a re-run. Each export
is kept as a version: its number, format, who asked, the report's content hash, the run's receipt
hash (the documents, prompts, model and verdicts it came from) and a snapshot hash of the case
as it stood - every finding's status and every evidence item. Two exports with the same snapshot
hash were made from the same state of the case; a different one says what moved.

Kept beside the run archives, in a folder per organisation (Phase 1c).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.auth.tenancy import current_org
from app.core.config import get_settings
from app.schemas.common import JarvisModel, utcnow
from app.schemas.investigation_report import InvestigationReport


class ReportVersion(JarvisModel):
    version: int
    format: str
    report_id: str
    content_hash: str
    receipt_hash: str
    snapshot_hash: str
    findings: dict[str, str] = Field(default_factory=dict)  # finding id -> its standing
    evidence: list[str] = Field(default_factory=list)
    actor: str = ""
    exported_at: datetime = Field(default_factory=utcnow)


def _path(run_id: str) -> Path:
    return get_settings().agent_dir / "runs" / "reports" / current_org() / f"{run_id}.json"


def versions(run_id: str) -> list[ReportVersion]:
    path = _path(run_id)
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ReportVersion.model_validate(item) for item in raw]


def snapshot(report: InvestigationReport) -> tuple[dict[str, str], list[str], str]:
    """The case's state the report was made from, and its hash."""
    findings = {
        **{f.finding_id: f"established {f.verification}" for f in report.established},
        **{f.finding_id: f"awaiting review {f.verification}" for f in report.awaiting_review},
        **{f.finding_id: f"not established {f.verification}" for f in report.not_established},
    }
    evidence = sorted(e.evidence_id or e.document for e in report.evidence)
    canonical = json.dumps({"findings": findings, "evidence": evidence}, sort_keys=True)
    return findings, evidence, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(report: InvestigationReport, fmt: str, actor: str) -> ReportVersion:
    existing = versions(report.run_id)
    findings, evidence, snapshot_hash = snapshot(report)
    version = ReportVersion(
        version=len(existing) + 1,
        format=fmt,
        report_id=report.report_id,
        content_hash=report.content_hash,
        receipt_hash=report.receipt_hash,
        snapshot_hash=snapshot_hash,
        findings=findings,
        evidence=evidence,
        actor=actor,
    )
    path = _path(report.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_text(
        json.dumps([v.model_dump(mode="json") for v in [*existing, version]], indent=1),
        encoding="utf-8",
    )
    temporary.replace(path)
    return version
