"""Which language engine may serve a request (v4 Phase 0 policy, enforced in Phase 7).

- **Confidential and Restricted** material stays in our cloud: only the open-source engine serves
  it, whatever the organisation's setting says. Material whose sensitivity is unknown is treated as
  Confidential.
- **Unclassified and Internal** material may go to Bhashini, when Bhashini is configured and the
  organisation's policy (`ops/governance.Policy.bhashini`) allows that level. Each organisation can
  only tighten this: "off", "unclassified", or "internal".

The open-source engine is always last in the list, so a Bhashini failure falls back to it.
"""

from __future__ import annotations

from app.integrations.bhashini import Bhashini
from app.schemas.evidence_locker import EvidenceClassification

OPEN_SOURCE = "open-source"
BHASHINI = "bhashini"

_ALLOWED: dict[str, set[EvidenceClassification]] = {
    "off": set(),
    "unclassified": {EvidenceClassification.UNCLASSIFIED},
    "internal": {EvidenceClassification.UNCLASSIFIED, EvidenceClassification.INTERNAL},
}


def bhashini_allowed(sensitivity: EvidenceClassification | None, setting: str) -> bool:
    level = sensitivity or EvidenceClassification.CONFIDENTIAL
    return level in _ALLOWED.get(setting, set())


def engines_for(sensitivity: EvidenceClassification | None) -> list[str]:
    """The engines that may serve material of this sensitivity, in order of preference."""
    from app.ops.governance import policy

    if Bhashini.configured() and bhashini_allowed(sensitivity, policy().bhashini):
        return [BHASHINI, OPEN_SOURCE]
    return [OPEN_SOURCE]


def strictest(levels: list[EvidenceClassification | None]) -> EvidenceClassification | None:
    """The most sensitive of several levels - a case's, from its files. Unknown counts as
    Confidential; no levels at all is unknown."""
    order = list(EvidenceClassification)
    known = [level or EvidenceClassification.CONFIDENTIAL for level in levels]
    return max(known, key=order.index) if known else None
