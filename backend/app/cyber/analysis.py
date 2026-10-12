"""What a set of security logs shows, read without a model (Phase 52).

From every line that parses as an event: the indicators (refanged), the entities - hosts, accounts,
processes, addresses, domains - and how they connect, each connection with the lines it rests on;
per-host and per-account timelines; and encoded PowerShell, decoded. Every item cites its lines, so
it can be checked against the log the way a finding is checked against a document.

Relationships are **observed**: each is one or more events that state it. Phase 53 adds inferred
edges (an attack path) and keeps them apart, named as such.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections import defaultdict

from app.cyber.eventlog import Event, from_line, sort_key
from app.cyber.iocs import IocKind, extract
from app.schemas.cyber import (
    CyberAnalysis,
    CyberEntity,
    CyberEvent,
    CyberRelation,
    DecodedCommand,
    IndicatorSighting,
    TimelineItem,
)
from app.tools.loader import source_ref

# Windows logon event ids, and the logon types that mean "from another machine".
LOGON_EVENTS = {"4624", "4625", "4648"}
REMOTE_LOGON_TYPES = {"3", "10"}
SERVICE_INSTALL = {"7045", "4697"}
_ENCODED = re.compile(
    r"-(?:e|en|enc|enco|encod|encode|encoded|encodedcommand)\s+([A-Za-z0-9+/]{16,}={0,2})",
    re.IGNORECASE,
)


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path.strip('"'))[-1].lower() if path else ""


def decode_powershell(command: str) -> str:
    """The script behind `powershell -enc <base64>`: UTF-16LE, as PowerShell encodes it."""
    match = _ENCODED.search(command)
    if not match:
        return ""
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError):
        return ""
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.isprintable() or all(c.isprintable() or c.isspace() for c in text):
            return text
    return ""


def with_decoded(line: str) -> str:
    """The line, with its encoded PowerShell decoded beside it when it carries one."""
    script = decode_powershell(line)
    return f"{line} [decoded -EncodedCommand: {script}]" if script else line


def analyse(
    documents: dict[str, str], page_starts: dict[str, list[int]] | None = None
) -> CyberAnalysis:
    page_starts = page_starts or {}
    events: list[CyberEvent] = []
    for name, text in documents.items():
        for number, line in enumerate(text.splitlines(), start=1):
            event = from_line(line)
            if event is None:
                continue
            events.append(
                CyberEvent(
                    locator=source_ref(name, number, page_starts),
                    time=event.time,
                    host=event.host,
                    user=event.user,
                    event=event.event,
                    summary=_summary(event),
                    fields=event.fields,
                )
            )
    events.sort(key=lambda e: (sort_key(Event(time=e.time)), e.locator))

    sightings: dict[tuple[str, str], IndicatorSighting] = {}
    entities: dict[tuple[str, str], CyberEntity] = {}
    relations: dict[tuple[str, str, str], CyberRelation] = {}
    decoded: list[DecodedCommand] = []

    def entity(kind: str, name: str, locator: str) -> str:
        if not name:
            return ""
        key = (kind, name.lower())
        found = entities.setdefault(key, CyberEntity(kind=kind, name=name))
        if locator not in found.sources:
            found.sources.append(locator)
        return f"{kind}:{name.lower()}"

    def relate(subject: str, predicate: str, obj: str, locator: str, time: str) -> None:
        if not subject or not obj:
            return
        key = (subject, predicate, obj)
        found = relations.setdefault(
            key, CyberRelation(subject=subject, predicate=predicate, object=obj, first_seen=time)
        )
        if locator not in found.sources:
            found.sources.append(locator)
        found.last_seen = time or found.last_seen
        if time and (not found.first_seen or time < found.first_seen):
            found.first_seen = time

    def sight(text: str, locator: str, via: str = "") -> None:
        for ioc in extract(text, locator):
            key = (ioc.kind.value, ioc.value.lower())
            found = sightings.setdefault(
                key,
                IndicatorSighting(kind=ioc.kind.value, value=ioc.value, defanged=bool(ioc.written)),
            )
            if locator not in found.sources:
                found.sources.append(locator)
            if via and via not in found.via:
                found.via.append(via)
            if ioc.kind in (IocKind.IPV4, IocKind.DOMAIN):
                entity(ioc.kind.value, ioc.value, locator)

    for e in events:
        loc, time = e.locator, e.time
        host = entity("host", e.host, loc)
        account = entity("account", e.user, loc)
        image = _basename(e.fields.get("image", ""))
        process = entity("process", image, loc)
        parent = entity("process", _basename(e.fields.get("parent", "")), loc)
        line = documents_line(documents, loc, page_starts) or e.summary
        sight(line, loc)

        if account and host:
            remote = e.event in LOGON_EVENTS and e.fields.get("logon_type") in REMOTE_LOGON_TYPES
            relate(account, "LOGGED_ON_REMOTELY" if remote else "ACTIVE_ON", host, loc, time)
        if process and host:
            relate(process, "RAN_ON", host, loc, time)
        if parent and process:
            relate(parent, "SPAWNED", process, loc, time)
        src = e.fields.get("src_ip", "")
        if src and host:
            relate(entity("ipv4", src, loc), "CONNECTED_TO", host, loc, time)
        dst = e.fields.get("dst_ip", "")
        if dst and host:
            port = e.fields.get("dst_port", "")
            relate(host, "CONNECTED_TO", entity("ipv4", dst, loc), loc, time)
            if port:
                found = relations[(host, "CONNECTED_TO", f"ipv4:{dst.lower()}")]
                if f"port {port}" not in found.detail:
                    found.detail = ", ".join(filter(None, [found.detail, f"port {port}"]))
        service = e.fields.get("service", "")
        if e.event in SERVICE_INSTALL and service and host:
            relate(entity("service", service, loc), "INSTALLED_ON", host, loc, time)

        script = decode_powershell(e.fields.get("cmd", ""))
        if script:
            decoded.append(DecodedCommand(locator=loc, host=e.host, user=e.user, script=script))
            sight(script, loc, via="decoded from -EncodedCommand")
            if process:
                relate(
                    process, "RAN_ENCODED_COMMAND", entity("script", script[:60], loc), loc, time
                )

    by_host: dict[str, list[TimelineItem]] = defaultdict(list)
    by_account: dict[str, list[TimelineItem]] = defaultdict(list)
    for e in events:
        item = TimelineItem(time=e.time, locator=e.locator, summary=e.summary)
        if e.host:
            by_host[e.host].append(item)
        if e.user:
            by_account[e.user].append(item)

    return CyberAnalysis(
        events=len(events),
        documents=sorted({e.locator.rsplit(":", 1)[0] for e in events}),
        indicators=sorted(sightings.values(), key=lambda s: (s.kind, s.value)),
        entities=sorted(entities.values(), key=lambda x: (x.kind, x.name.lower())),
        relations=sorted(relations.values(), key=lambda r: (r.first_seen, r.subject, r.object)),
        host_timelines=dict(sorted(by_host.items())),
        account_timelines=dict(sorted(by_account.items())),
        decoded_commands=decoded,
    )


def documents_line(
    documents: dict[str, str], locator: str, page_starts: dict[str, list[int]]
) -> str:
    """The text of a row locator's line. Page locators fall back to the event summary."""
    name, _, position = locator.rpartition(":")
    if not position.startswith("r"):
        return ""
    lines = documents.get(name, "").splitlines()
    index = int(position[1:]) - 1
    return lines[index] if 0 <= index < len(lines) else ""


def _summary(event: Event) -> str:
    parts = [f"event {event.event}" if event.event else ""]
    for name in ("user", "image", "cmd", "src_ip", "dst_ip", "service", "message"):
        value = event.get(name)
        if value:
            parts.append(f"{name} {value[:120]}")
    return "; ".join(p for p in parts if p)
