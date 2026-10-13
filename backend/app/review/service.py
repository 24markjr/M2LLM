"""Review rules, decisions and the audit log (Phase 50).

Like the Evidence Locker and cases: Postgres when the database answers, memory otherwise (named),
and recording never fails the work it records (invariant 10) - except a review decision itself,
which a reviewer must see succeed or fail.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field

from app.core.agent_config import load_yaml
from app.core.config import get_settings
from app.core.logging import get_logger
from app.review.store import MemoryReviewStore, ReviewStore
from app.schemas.common import JarvisModel
from app.schemas.finding import Finding, StatementType
from app.schemas.review import AuditEntry, FindingReview, ReviewDecision, ReviewState
from app.schemas.verification import IssueType

log = get_logger(__name__)

_memory_store = MemoryReviewStore()
# Probed once per process; tests set it False (tests/conftest.py).
_database: bool | None = None
_checked_at: float | None = None


def reset_review_store_probe() -> None:
    global _database, _checked_at
    _database, _checked_at = None, None


async def get_review_store() -> ReviewStore:
    global _database, _checked_at
    from app.database.session import recheck

    _database, _checked_at = await recheck(_database, _checked_at)
    if _database:
        from app.database.review_store import PgReviewStore

        return PgReviewStore()
    return _memory_store


async def audit(action: str, *, actor: str = "system", target: str = "", **details: Any) -> None:
    """Add one entry to the audit log. Never raises: an unrecorded action is logged, not fatal."""
    try:
        await (await get_review_store()).record(
            AuditEntry(actor=actor, action=action, target=target, details=details)
        )
    except Exception as exc:  # noqa: BLE001 - the log must never fail the work it records
        log.warning("audit_not_recorded", action=action, error=str(exc))


# --- what needs review ----------------------------------------------------------------------------


class ReviewRules(JarvisModel):
    contradiction: bool = True
    described_only: bool = True
    challenged: bool = True
    risk_or_recommendation: bool = True
    case_severity: list[str] = Field(default_factory=lambda: ["HIGH", "CRITICAL"])
    attack_mapping: bool = True


def get_review_rules() -> ReviewRules:
    return _rules(str(get_settings().agent_dir))


@lru_cache
def _rules(agent_dir: str) -> ReviewRules:
    if not (Path(agent_dir) / "config" / "review.yaml").exists():
        return ReviewRules()
    raw = load_yaml("review.yaml").get("rules", {})
    return ReviewRules.model_validate(raw if isinstance(raw, dict) else {})


def requirements(
    finding: Finding,
    *,
    case_severity: str = "",
    challenge_outcome: str = "",
    attack_mapped: bool = False,
) -> list[str]:
    """Why this finding needs a person's review, in words; empty when it does not."""
    rules = get_review_rules()
    reasons: list[str] = []
    if rules.contradiction and finding.statement_type is StatementType.CONTRADICTION:
        reasons.append("it reports a contradiction")
    if (
        rules.described_only
        and finding.verification is not None
        and any(i.issue_type is IssueType.DESCRIBED_ONLY for i in finding.verification.issues)
    ):
        reasons.append("the verifier found it only described, not established")
    if rules.challenged and challenge_outcome in ("CONTESTED", "OVERTURNED"):
        reasons.append(f"a challenge {challenge_outcome.lower()} it")
    if rules.risk_or_recommendation and finding.statement_type in (
        StatementType.RISK,
        StatementType.RECOMMENDATION,
    ):
        reasons.append(f"it is a {finding.statement_type.value.lower()}: a judgement")
    if case_severity and case_severity in rules.case_severity:
        reasons.append(f"its case is {case_severity}")
    if rules.attack_mapping and attack_mapped:
        reasons.append("it maps to a MITRE ATT&CK technique")
    return reasons


def review_of(
    run_id: str,
    finding: Finding,
    decisions: list[ReviewDecision],
    reasons: list[str],
) -> FindingReview:
    history = [d for d in decisions if d.finding_id == finding.finding_id]
    state = history[-1].state if history else ReviewState.PENDING
    return FindingReview(
        run_id=run_id,
        finding_id=finding.finding_id,
        claim=finding.claim,
        statement_type=finding.statement_type.value,
        required=bool(reasons),
        required_because=reasons,
        state=state,
        history=history,
    )


def counts_as_established(finding: Finding, review: FindingReview | None) -> bool:
    """Whether a finding counts (memory, the report's established findings): verified, and either
    not requiring review or approved / modified by a reviewer."""
    if not finding.is_verified:
        return False
    return review is None or review.settled
