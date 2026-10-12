"""Vendor MITRE ATT&CK (Phase 53, decision D14): the official STIX bundle, reduced and pinned.

    python scripts/vendor_attack.py path/to/enterprise-attack.json

Reads the official Enterprise ATT&CK STIX 2.1 bundle (pinned: v15.1, from
https://github.com/mitre/cti, tag ATT&CK-v15.1) and writes `.agent/attack/enterprise-attack.json`:
every technique and sub-technique that is neither revoked nor deprecated - its ATT&CK id, name,
tactics and URL - and the tactics in kill-chain order, stamped with the bundle's version and
SHA-256. The full bundle is 26 MB; the extract is what the mapping reads, offline. Re-running this
on the same bundle reproduces the extract byte for byte, which is how it is checked.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SOURCE = (
    "https://raw.githubusercontent.com/mitre/cti/ATT%26CK-v15.1/enterprise-attack/"
    "enterprise-attack.json"
)
VERSION = "15.1"
TARGET = Path(__file__).resolve().parents[2] / ".agent" / "attack" / "enterprise-attack.json"


def _attack_id(obj: dict[str, object]) -> str:
    for ref in obj.get("external_references", []) or []:  # type: ignore[union-attr]
        if isinstance(ref, dict) and ref.get("source_name") == "mitre-attack":
            return str(ref.get("external_id", ""))
    return ""


def _url(obj: dict[str, object]) -> str:
    for ref in obj.get("external_references", []) or []:  # type: ignore[union-attr]
        if isinstance(ref, dict) and ref.get("source_name") == "mitre-attack":
            return str(ref.get("url", ""))
    return ""


def extract(raw: bytes) -> dict[str, object]:
    bundle = json.loads(raw)
    objects = bundle["objects"]
    live = [o for o in objects if not o.get("revoked") and not o.get("x_mitre_deprecated")]
    tactics = {
        o["x_mitre_shortname"]: {"id": _attack_id(o), "name": o["name"]}
        for o in live
        if o.get("type") == "x-mitre-tactic"
    }
    matrix = next(o for o in live if o.get("type") == "x-mitre-matrix")
    order = {}
    by_ref = {o["id"]: o for o in live if o.get("type") == "x-mitre-tactic"}
    for index, ref in enumerate(matrix.get("tactic_refs", [])):
        if ref in by_ref:
            order[by_ref[ref]["x_mitre_shortname"]] = index
    techniques = sorted(
        (
            {
                "id": _attack_id(o),
                "name": o["name"],
                "tactics": sorted(
                    (
                        p["phase_name"]
                        for p in o.get("kill_chain_phases", [])
                        if p.get("kill_chain_name") == "mitre-attack"
                    ),
                    key=lambda t: order.get(t, 99),
                ),
                "subtechnique": bool(o.get("x_mitre_is_subtechnique")),
                "url": _url(o),
            }
            for o in live
            if o.get("type") == "attack-pattern" and _attack_id(o)
        ),
        key=lambda t: str(t["id"]),
    )
    return {
        "source": SOURCE,
        "version": VERSION,
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "tactics": [
            {"shortname": name, **tactics[name]}
            for name in sorted(tactics, key=lambda n: order.get(n, 99))
        ],
        "techniques": techniques,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    raw = Path(sys.argv[1]).read_bytes()
    data = extract(raw)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {TARGET} ({len(data['techniques'])} techniques, {len(data['tactics'])} tactics)")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    sys.exit(main())
