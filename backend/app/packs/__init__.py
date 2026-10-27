"""Domain packs (v4 Phase 10): what changes between a financial audit, a procurement review, a
cyber incident and a project assurance - kept as data, one YAML file a pack, in `.agent/packs/`.

A pack sets:

- **attributes** - the names values are recorded under (`po_number`, `approved_amount`), handed to
  knowledge extraction as known attribute names so the same value is named the same way across
  documents;
- **severity** - phrases that raise a finding's severity, each with its reason in the report
  ("duplicate payment: HIGH under the financial-audit pack");
- **report** - the report's title and the names of its sections;
- **starter questions** - what an investigator of this kind usually asks first.

An organisation chooses its pack (Data governance); `general` changes nothing. A pack never touches
verification: what counts as evidence is the same in every domain.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field

from app.core.config import get_settings
from app.schemas.common import JarvisModel
from app.schemas.investigation_report import Severity

DEFAULT_PACK = "general"


class ReportWords(JarvisModel):
    title: str = "Investigation Report"
    brief: str = "Executive brief"
    findings: str = "Findings"
    contradictions: str = "Contradictions"
    gaps: str = "Gaps and next evidence"


class Pack(JarvisModel):
    id: str
    name: str
    description: str = ""
    attributes: list[str] = Field(default_factory=list)
    # Severity -> phrases. A finding whose claim contains a phrase is raised to that severity.
    severity: dict[Severity, list[str]] = Field(default_factory=dict)
    report: ReportWords = Field(default_factory=ReportWords)
    starter_questions: list[str] = Field(default_factory=list)

    def severity_for(self, claim: str) -> tuple[Severity, str] | None:
        """The highest severity a phrase of this pack gives the claim, and why."""
        lowered = claim.lower()
        for level in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            for phrase in self.severity.get(level, []):
                if phrase.lower() in lowered:
                    return level, f'"{phrase}" is {level.value} under the {self.name} pack'
        return None


def packs_dir() -> Path:
    return get_settings().agent_dir / "packs"


@lru_cache(maxsize=32)
def _load(path: str, mtime: float) -> Pack:
    return Pack.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def all_packs() -> list[Pack]:
    folder = packs_dir()
    found = [_load(str(p), p.stat().st_mtime) for p in sorted(folder.glob("*.yaml"))]
    return found or [Pack(id=DEFAULT_PACK, name="General")]


def get_pack(pack_id: str) -> Pack:
    return next((p for p in all_packs() if p.id == pack_id), Pack(id=DEFAULT_PACK, name="General"))


def current_pack() -> Pack:
    """The pack of the organisation this request or run belongs to."""
    from app.ops.governance import policy

    return get_pack(policy().pack)
