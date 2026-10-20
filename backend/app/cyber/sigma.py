"""Sigma rules as ATT&CK mapping rules (Phase B5).

Detections written in the Sigma format (`.agent/attack/sigma/*.yml`) are converted into the same
`Rule` model as `.agent/config/attack_rules.yaml`, so a Sigma match is cited, mapped and reviewed
exactly like one of those. The supported subset is the common one - `selection*` blocks joined by
`and` / `or`, the modifiers `contains`, `startswith`, `endswith` and none - and a rule outside it is
skipped with the reason logged, never half-applied.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger

log = get_logger(__name__)

# Sigma's Windows field names -> the normalised event fields the mapper reads (eventlog.py).
FIELDS = {
    "Image": "image",
    "NewProcessName": "image",
    "ParentImage": "parent",
    "CommandLine": "cmd",
    "EventID": "event",
    "LogonType": "logon_type",
    "DestinationPort": "dst_port",
    "DestinationIp": "dst_ip",
    "User": "user",
    "TargetUserName": "user",
    "SubjectUserName": "user",
    "Computer": "host",
    "ServiceName": "service",
}
_TAG = re.compile(r"^attack\.(t\d{4}(?:\.\d{3})?)$", re.IGNORECASE)


class Unsupported(ValueError):
    """A Sigma construct outside the supported subset."""


def _regex(modifier: str, values: Any) -> str:
    options = values if isinstance(values, list) else [values]
    escaped = [re.escape(str(v)) for v in options]
    body = escaped[0] if len(escaped) == 1 else "(" + "|".join(escaped) + ")"
    if modifier == "contains":
        return body
    if modifier == "endswith":
        return body + "$"
    if modifier == "startswith":
        return "^" + body
    if modifier == "":
        return "^" + body + "$"
    raise Unsupported(f"modifier '{modifier}'")


def _conditions(selection: Any) -> list[dict[str, str]]:
    if not isinstance(selection, dict):
        raise Unsupported("a selection that is not a map of fields")
    out = []
    for key, values in selection.items():
        name, _, modifier = str(key).partition("|")
        if name not in FIELDS:
            raise Unsupported(f"field '{name}'")
        out.append({"field": FIELDS[name], "regex": _regex(modifier, values)})
    return out


def convert(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """One Sigma rule as mapping rules: one per technique tag and per `or` branch."""
    techniques = [m.group(1).upper() for t in rule.get("tags", []) if (m := _TAG.match(str(t)))]
    if not techniques:
        raise Unsupported("no attack.tNNNN tag")
    detection = rule.get("detection") or {}
    condition = str(detection.get("condition", "")).strip()
    if re.search(r"\bnot\b|\bof\b|[()|*]", condition):
        raise Unsupported(f"condition '{condition}'")
    branches = [
        [name.strip() for name in part.split(" and ")] for part in condition.split(" or ") if part
    ]
    why = f"Sigma: {rule.get('title', 'untitled rule')}"
    out = []
    for names in branches:
        conditions = [c for name in names for c in _conditions(detection.get(name))]
        out += [{"technique": t, "why": why, "all": conditions} for t in techniques]
    return out


def load_sigma(directory: Path) -> list[dict[str, Any]]:
    """Every supported rule in `directory`; unsupported ones logged and skipped."""
    rules: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yml")):
        try:
            rules += convert(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except (Unsupported, yaml.YAMLError) as exc:
            log.warning("sigma_rule_skipped", file=path.name, reason=str(exc))
    return rules
