"""Source authority: how much weight a source carries (Phase 45, decision D18).

A tier per evidence item, set at intake by the rules in `.agent/config/authority.yaml` and
overridable by a person. Reported on both sides of a contradiction and never used to resolve one:
an approved statement and a draft email that disagree still disagree, and saying which side is
official is information for the reader, not a verdict.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field

from app.core.agent_config import AgentConfigError, load_yaml
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel

log = get_logger(__name__)


class AuthorityTier(JarvisModel):
    id: str = Field(pattern=r"^[A-Z_]{2,32}$")
    label: str
    description: str = ""
    # The factor Phase 46 records in confidence. Not read before then.
    weight: float = Field(ge=0.0, le=1.0)


class AuthorityRule(JarvisModel):
    pattern: str
    tier: str


class AuthorityConfig(JarvisModel):
    version: int = 1
    tiers: list[AuthorityTier]
    rules: list[AuthorityRule] = Field(default_factory=list)
    default: str = "UNASSESSED"

    def tier(self, tier_id: str) -> AuthorityTier | None:
        return next((t for t in self.tiers if t.id == tier_id), None)


# With no authority.yaml every source is unassessed: authority is information for the reader, and
# its absence must not stop a mission. A malformed file still fails loudly.
_NEUTRAL = AuthorityConfig(
    tiers=[AuthorityTier(id="UNASSESSED", label="Not assessed", weight=0.75)],
    default="UNASSESSED",
)


def get_authority_config() -> AuthorityConfig:
    """The tiers and rules for the current `.agent` directory, cached per directory (tests point
    the settings at temporary ones)."""
    return _load(str(get_settings().agent_dir))


@lru_cache
def _load(agent_dir: str) -> AuthorityConfig:
    if not (Path(agent_dir) / "config" / "authority.yaml").exists():
        log.warning("authority_config_missing", fallback="UNASSESSED")
        return _NEUTRAL
    config = AuthorityConfig.model_validate(load_yaml("authority.yaml"))
    known = {t.id for t in config.tiers}
    for tier_id in [config.default, *(r.tier for r in config.rules)]:
        if tier_id not in known:
            raise AgentConfigError(f"authority.yaml names an unknown tier: {tier_id}")
    for rule in config.rules:
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            raise AgentConfigError(f"authority.yaml: bad pattern {rule.pattern!r}: {exc}") from exc
    return config


def tier_for_name(name: str) -> tuple[str, str]:
    """The tier the intake rules give a file name, and why, in words."""
    config = get_authority_config()
    for rule in config.rules:
        match = re.search(rule.pattern, name, re.IGNORECASE)
        if match:
            return rule.tier, f'set at intake: the name contains "{match.group(0)}"'
    return config.default, "set at intake: no rule matched the name"


def is_tier(tier_id: str) -> bool:
    return get_authority_config().tier(tier_id) is not None


def label(tier_id: str) -> str:
    tier = get_authority_config().tier(tier_id)
    return tier.label if tier else tier_id


def authority_map(names: list[str], known: dict[str, str] | None = None) -> dict[str, str]:
    """Each document's tier: the Evidence Locker's where it has one, the intake rules otherwise
    (the CLI and the evaluation read files without a locker)."""
    known = known or {}
    return {name: known.get(name) or tier_for_name(name)[0] for name in names}
