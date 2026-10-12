"""Other cases that share indicators with this one - context, never evidence (Phase 52, D19).

Opt-in per case. Compared on distinctive indicators only - domains, URLs, file hashes, e-mail
addresses, CVEs and public IP addresses; a private address like 10.0.0.12 is in half the networks in
the world and says nothing about two cases being related.

Read from the other cases' evidence as stored (content-addressed, Phase 43), analysed the same way.
What comes back is shown beside the analysis, labelled as context. It never enters a mission: it is
not an observation, has no locator a finding could cite, and a test checks that a run in a case that
opted in produces the same observations as one that did not.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

from app.cases.service import get_case_store
from app.core.logging import get_logger
from app.cyber.analysis import analyse
from app.cyber.eventlog import events_from_json, events_from_xml, to_line
from app.evidence import store as evidence_store
from app.evidence.service import get_locker
from app.schemas.case import CaseMode
from app.schemas.cyber import IndicatorSighting, SimilarCase

log = get_logger(__name__)

DISTINCTIVE = frozenset({"domain", "url", "sha256", "sha1", "md5", "email", "cve"})
# How many other cases are compared, newest first: recall is a hint, not a search engine.
MAX_CASES = 50


def distinctive(indicators: list[IndicatorSighting]) -> set[str]:
    values: set[str] = set()
    for sighting in indicators:
        if sighting.kind in DISTINCTIVE:
            values.add(sighting.value.lower())
        elif sighting.kind == "ipv4":
            try:
                address = ipaddress.IPv4Address(sighting.value)
            except ValueError:
                continue
            # Named networks, not `is_private` / `is_global`: the standard library counts the
            # documentation ranges incident write-ups use (203.0.113.0/24) as private.
            if not any(address in network for network in LOCAL_NETWORKS) and not (
                address.is_multicast or address.is_unspecified
            ):
                values.add(sighting.value)
    return values


LOCAL_NETWORKS = tuple(
    ipaddress.IPv4Network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
    )
)


def as_lines(name: str, raw: str) -> str:
    """A stored original read the way a mission reads it: event exports one event per line."""
    suffix = Path(name).suffix.lower()
    try:
        if suffix == ".xml":
            return "\n".join(to_line(e) for e in events_from_xml(raw))
        if suffix in (".json", ".jsonl", ".ndjson"):
            events = events_from_json(raw)
            if events:
                return "\n".join(to_line(e) for e in events)
    except (ValueError, SyntaxError):
        return raw
    return raw


async def similar_cases(case_id: str, indicators: set[str]) -> list[SimilarCase]:
    """Other CYBER cases whose evidence shares a distinctive indicator. Never raises."""
    if not indicators:
        return []
    found: list[SimilarCase] = []
    try:
        cases = await get_case_store()
        locker = await get_locker()
        others = [
            c for c in await cases.cases() if c.case_id != case_id and c.mode is CaseMode.CYBER
        ][:MAX_CASES]
        for other in others:
            documents: dict[str, str] = {}
            for link in await cases.evidence(other.case_id):
                item = await locker.get(link.evidence_id)
                path = evidence_store.path_for(item.sha256) if item else None
                if item is None or path is None or not path.is_file():
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
                documents[item.name] = as_lines(item.name, raw)
            shared = indicators & distinctive(analyse(documents).indicators)
            if shared:
                runs = await cases.investigations(other.case_id)
                found.append(
                    SimilarCase(
                        case_id=other.case_id,
                        run_id=runs[-1].run_id if runs else "",
                        shared=sorted(shared),
                    )
                )
    except Exception as exc:  # noqa: BLE001 - recall is a hint; it never fails the analysis
        log.warning("recall_failed", case_id=case_id, error=str(exc))
    return found
