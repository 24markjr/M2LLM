"""The prompt-injection detection suite (Phase 27).

Ported from Member 4's `security/security_test_suite.py`, which ran its 14 cases and reported
`correct / total` as the "injection detection rate". That definition is kept, so the headline
number means what it meant in their dashboard. Three more figures are reported beside it, because
one number over attacks and clean documents together hides which way it fails:

| Figure | Definition |
|---|---|
| `detection_rate` | Member 4's: cases classified correctly (flagged or not) / all cases |
| `attack_recall` | attacks flagged / attacks |
| `false_positive_rate` | clean cases flagged / clean cases |
| `category_misses` | attacks flagged, but not under the expected category |

Cases live in `.agent/evals/security/injection_cases.yaml`, with each case's source recorded:
Member 4's verbatim, this repository's adversarial suite, attacks on JARVIS's own surfaces, and
realistic clean text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from app.core.config import get_settings
from app.schemas.common import JarvisModel, UnitFloat
from app.security.injection import scan


class SecurityCase(JarvisModel):
    id: str
    source: str
    flag: bool
    text: str
    expect: str = ""


class SecurityCaseResult(JarvisModel):
    id: str
    source: str
    expected_flag: bool
    flagged: bool
    categories: list[str] = Field(default_factory=list)
    severity: str
    correct: bool
    category_ok: bool = True


class SecurityReport(JarvisModel):
    cases: int
    detection_rate: UnitFloat
    attack_recall: UnitFloat
    false_positive_rate: UnitFloat
    category_misses: int = 0
    results: list[SecurityCaseResult] = Field(default_factory=list)

    @property
    def failures(self) -> list[SecurityCaseResult]:
        return [r for r in self.results if not r.correct or not r.category_ok]


def cases_path() -> Path:
    return get_settings().agent_dir / "evals" / "security" / "injection_cases.yaml"


def load_cases(path: Path | None = None) -> list[SecurityCase]:
    raw: dict[str, Any] = yaml.safe_load((path or cases_path()).read_text(encoding="utf-8"))
    return [SecurityCase.model_validate(case) for case in raw.get("cases", [])]


def run_security_suite(path: Path | None = None) -> SecurityReport:
    results: list[SecurityCaseResult] = []
    for case in load_cases(path):
        found = scan(case.text, source=case.id)
        results.append(
            SecurityCaseResult(
                id=case.id,
                source=case.source,
                expected_flag=case.flag,
                flagged=found.flagged,
                categories=sorted(found.hits),
                severity=found.severity.value,
                correct=found.flagged == case.flag,
                category_ok=not (case.flag and case.expect and case.expect not in found.hits),
            )
        )

    attacks = [r for r in results if r.expected_flag]
    clean = [r for r in results if not r.expected_flag]
    return SecurityReport(
        cases=len(results),
        detection_rate=sum(r.correct for r in results) / len(results) if results else 0.0,
        attack_recall=sum(r.flagged for r in attacks) / len(attacks) if attacks else 0.0,
        false_positive_rate=sum(r.flagged for r in clean) / len(clean) if clean else 0.0,
        category_misses=sum(not r.category_ok for r in results),
        results=results,
    )
