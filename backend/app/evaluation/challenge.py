"""The challenge benchmark: planted false findings and true ones (Phase 48).

A small corpus about one programme, four documents of four authorities - an approved plan, a
status report, a vendor's email and draft minutes - and twelve findings with known truth. Each is
challenged with the deterministic rule alone (no model), so this runs in CI like the trust
benchmark.

- `challenge_catch_rate`: the share of false findings the challenge did not let stand (CONTESTED or
  OVERTURNED);
- `challenge_false_alarm_rate`: the share of true findings it OVERTURNED.

A true finding that a weaker source disagrees with is CONTESTED, and that is right: the disagreement
exists. Only overturning a true finding is a false alarm.

**What it shows and does not.** Every disagreement here is on a date, a figure or a negation, except
one: a false vendor name, which the rule cannot see and the benchmark keeps as a known miss. The
corpus was written for this rule; a perfect score would show the rule does what it says, not that it
generalises.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.core.config import get_settings
from app.intelligence.challenge import ChallengeOutcome, challenge
from app.intelligence.confidence import rescore
from app.intelligence.reasoning.statements import type_statements
from app.schemas.common import JarvisModel, SourceLocator, UnitFloat, utcnow
from app.schemas.evidence import ClaimElement, EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.verification import VerificationResult, VerificationStatus

CORPUS: dict[str, str] = {
    "atlas_approved_plan.txt": (
        "ATLAS PROGRAMME - APPROVED PLAN\n"
        "The Atlas go-live date is 12 June 2026.\n"
        "The approved Atlas budget is 480,000.\n"
        "Atlas phase 2 was cancelled by the steering committee.\n"
        "The Atlas vendor is Kestrel Systems.\n"
    ),
    "atlas_status_report.txt": (
        "ATLAS STATUS REPORT\n"
        "The Atlas go-live date remains 12 June 2026.\n"
        "Atlas spend to date is 210,000.\n"
        "Atlas phase 2 design work continues this month.\n"
        "Testing of the Atlas billing module starts on 4 May 2026.\n"
    ),
    "atlas_vendor_email.txt": (
        "Email from Kestrel Systems\n"
        "We expect the Atlas go-live on 26 June 2026 at the earliest.\n"
        "Our invoice for the Atlas licences is 95,000.\n"
    ),
    "atlas_minutes_draft.txt": (
        "DRAFT MINUTES\n"
        "The committee discussed raising the Atlas budget to 520,000.\n"
        "Testing of the Atlas billing module starts on 4 May 2026.\n"
    ),
}


class ChallengeCase(JarvisModel):
    case_id: str
    claim: str
    cites: list[str]
    true: bool
    note: str = ""


CASES: list[ChallengeCase] = [
    # Planted false findings: the challenge must not let them stand.
    ChallengeCase(
        case_id="false-golive-from-email",
        claim="The Atlas go-live date is 26 June 2026.",
        cites=["atlas_vendor_email.txt:r2"],
        true=False,
        note="the approved plan gives 12 June",
    ),
    ChallengeCase(
        case_id="false-budget-from-draft",
        claim="The approved Atlas budget is 520,000.",
        cites=["atlas_minutes_draft.txt:r2"],
        true=False,
        note="the approved plan gives 480,000",
    ),
    ChallengeCase(
        case_id="false-phase2-continues",
        claim="Atlas phase 2 continues.",
        cites=["atlas_status_report.txt:r4"],
        true=False,
        note="the approved plan says phase 2 was cancelled",
    ),
    ChallengeCase(
        case_id="false-testing-date",
        claim="Testing of the Atlas billing module starts on 18 May 2026.",
        cites=["atlas_status_report.txt:r5"],
        true=False,
        note="its own line and the draft minutes give 4 May",
    ),
    ChallengeCase(
        case_id="false-spend-figure",
        claim="Atlas spend to date is 250,000.",
        cites=["atlas_status_report.txt:r3"],
        true=False,
        note="its own cited line gives 210,000",
    ),
    ChallengeCase(
        case_id="false-vendor-name",
        claim="The Atlas vendor is Orion Freight.",
        cites=["atlas_vendor_email.txt:r1"],
        true=False,
        note="a wrong name: no date, figure or negation to disagree on - the known miss",
    ),
    # True findings: the challenge must not overturn them.
    ChallengeCase(
        case_id="true-golive",
        claim="The Atlas go-live date is 12 June 2026.",
        cites=["atlas_approved_plan.txt:r2"],
        true=True,
        note="the vendor's email disagrees, from a weaker source: contested, not overturned",
    ),
    ChallengeCase(
        case_id="true-budget",
        claim="The approved Atlas budget is 480,000.",
        cites=["atlas_approved_plan.txt:r3"],
        true=True,
        note="the draft minutes discuss 520,000: contested, not overturned",
    ),
    ChallengeCase(
        case_id="true-spend",
        claim="Atlas spend to date is 210,000.",
        cites=["atlas_status_report.txt:r3"],
        true=True,
    ),
    ChallengeCase(
        case_id="true-testing-date",
        claim="Testing of the Atlas billing module starts on 4 May 2026.",
        cites=["atlas_status_report.txt:r5"],
        true=True,
    ),
    ChallengeCase(
        case_id="true-vendor",
        claim="The Atlas vendor is Kestrel Systems.",
        cites=["atlas_approved_plan.txt:r5"],
        true=True,
    ),
    ChallengeCase(
        case_id="true-invoice",
        claim="Kestrel Systems invoiced 95,000 for the Atlas licences.",
        cites=["atlas_vendor_email.txt:r3"],
        true=True,
    ),
]


class ChallengeCaseResult(JarvisModel):
    case_id: str
    true: bool
    outcome: ChallengeOutcome
    summary: str
    confidence_before: float
    confidence_after: float

    @property
    def caught(self) -> bool:
        return not self.true and self.outcome is not ChallengeOutcome.WITHSTOOD

    @property
    def false_alarm(self) -> bool:
        return self.true and self.outcome is ChallengeOutcome.OVERTURNED


class ChallengeReport(JarvisModel):
    generated_at: datetime = Field(default_factory=utcnow)
    dataset_hash: str
    cases: int
    false_cases: int
    true_cases: int
    challenge_catch_rate: UnitFloat
    challenge_false_alarm_rate: UnitFloat
    results: list[ChallengeCaseResult] = Field(default_factory=list)


def dataset_hash() -> str:
    payload = json.dumps(
        {"corpus": CORPUS, "cases": [c.model_dump() for c in CASES]}, sort_keys=True
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _finding(case: ChallengeCase) -> Finding:
    refs = []
    for index, cite in enumerate(case.cites, start=1):
        document, row = cite.rsplit(":r", 1)
        refs.append(
            EvidenceRef(
                evidence_id=f"E-{index:03d}",
                locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
                resolution=ResolutionStatus.RESOLVED,
            )
        )
    finding = Finding(
        finding_id="F-001",
        claim=case.claim,
        evidence=refs,
        elements=[ClaimElement(text=case.claim, supported=True)],
        # As the run's verifier would have passed it: the challenge is what doubts it.
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    finding.classification = finding.classify()
    return finding


def _evidence_text() -> dict[str, str]:
    return {
        f"{name}:r{number}": line
        for name, text in CORPUS.items()
        for number, line in enumerate(text.splitlines(), start=1)
    }


async def run_challenge_benchmark() -> ChallengeReport:
    text = _evidence_text()
    results: list[ChallengeCaseResult] = []
    for case in CASES:
        finding = _finding(case)
        type_statements([finding], comparative=False)
        rescore([finding], evidence_text=text)
        outcome = await challenge(finding, CORPUS, evidence_text=text)
        results.append(
            ChallengeCaseResult(
                case_id=case.case_id,
                true=case.true,
                outcome=outcome.outcome,
                summary=outcome.summary,
                confidence_before=round(outcome.confidence_before, 3),
                confidence_after=round(outcome.confidence_after, 3),
            )
        )
    false_cases = [r for r in results if not r.true]
    true_cases = [r for r in results if r.true]
    return ChallengeReport(
        dataset_hash=dataset_hash(),
        cases=len(results),
        false_cases=len(false_cases),
        true_cases=len(true_cases),
        challenge_catch_rate=sum(r.caught for r in false_cases) / len(false_cases),
        challenge_false_alarm_rate=sum(r.false_alarm for r in true_cases) / len(true_cases),
        results=results,
    )


def challenge_dir() -> Path:
    return get_settings().agent_dir / "evals" / "challenge"


def write_challenge_report(report: ChallengeReport) -> tuple[Path, Path]:
    directory = challenge_dir() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%S")
    json_path = directory / f"{stamp}-challenge.json"
    md_path = directory / f"{stamp}-challenge.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Challenge benchmark",
        "",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M UTC}  ",
        f"**Dataset:** `{report.dataset_hash}` ({report.false_cases} false, "
        f"{report.true_cases} true findings)",
        "",
        "Deterministic, no model. Every figure is computed by `app/evaluation/challenge.py`.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| challenge_catch_rate | {report.challenge_catch_rate:.3f} |",
        f"| challenge_false_alarm_rate | {report.challenge_false_alarm_rate:.3f} |",
        "",
        "| Case | Truth | Outcome | Confidence | Why |",
        "|---|---|---|---|---|",
    ]
    for r in report.results:
        lines.append(
            f"| {r.case_id} | {'true' if r.true else 'false'} | {r.outcome.value} | "
            f"{r.confidence_before:.2f} -> {r.confidence_after:.2f} | {r.summary} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
