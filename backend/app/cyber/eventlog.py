"""Event logs as citable lines (Phase 52, decision D13).

A security log is evidence only if each event can be cited on its own. Formats that already put
one event on a line (syslog, CSV, JSON Lines) are read as they are; the ones that do not - a JSON
array of events, a Windows or Sysmon export as XML - are normalised to **one event per line**:

    2026-03-03T02:14:05Z host=WS-12 user=jdoe event=4688 image=powershell.exe cmd="powershell -enc"

so a finding cites `security.xml:r7` and the verifier reads exactly that event. Field names are
mapped from the common schemas (Windows Security, Sysmon, generic JSON) onto one short vocabulary;
anything unmapped is kept as `key=value`, never dropped.

Native `.evtx` (binary) is not read yet (D13: later); export it as XML or JSON.

XML is parsed with the standard library only after a document carrying a DTD or an entity
declaration is refused: an event export has no use for one, and refusing it closes the entity
expansion and external-entity attacks a security linter warns about.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ElementTree
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import JarvisModel

# Source field -> the short name in a normalised line. First match wins, so order is preference.
FIELDS: dict[str, tuple[str, ...]] = {
    "time": ("UtcTime", "TimeCreated", "SystemTime", "@timestamp", "timestamp", "time", "Date"),
    "host": ("Computer", "host", "hostname", "Hostname", "ComputerName", "device"),
    "user": ("TargetUserName", "User", "user", "SubjectUserName", "AccountName", "username"),
    "event": ("EventID", "event_id", "EventId", "eventid", "event"),
    "image": ("Image", "NewProcessName", "process", "ProcessName", "image"),
    "cmd": ("CommandLine", "command_line", "cmdline", "commandline"),
    "parent": ("ParentImage", "ParentProcessName", "parent_process", "parent"),
    "src_ip": ("SourceIp", "IpAddress", "src_ip", "source_ip", "SourceAddress"),
    "dst_ip": ("DestinationIp", "dst_ip", "destination_ip", "DestAddress"),
    "dst_port": ("DestinationPort", "dst_port", "destination_port"),
    "logon_type": ("LogonType", "logon_type"),
    "service": ("ServiceName", "service"),
    "domain": ("TargetDomainName", "QueryName", "domain"),
    "hash": ("Hashes", "hash", "sha256", "md5"),
    "message": ("Message", "message", "msg"),
}
ORDER = list(FIELDS)
_ALIASES = {alias.lower(): short for short, aliases in FIELDS.items() for alias in aliases}


class Event(JarvisModel):
    """One normalised event: the fields every analysis reads, and the rest as they came."""

    time: str = ""
    host: str = ""
    user: str = ""
    event: str = ""
    fields: dict[str, str] = Field(default_factory=dict)

    def get(self, name: str) -> str:
        return {"time": self.time, "host": self.host, "user": self.user, "event": self.event}.get(
            name, self.fields.get(name, "")
        )


def _value(raw: Any) -> str:
    text = str(raw).strip()
    return text.replace("\n", " ").replace("\r", " ")


def _quote(value: str) -> str:
    return f'"{value}"' if (" " in value or not value) else value


def normalise(record: dict[str, Any]) -> Event:
    """A record from any of the schemas, as one Event."""
    mapped: dict[str, str] = {}
    extra: dict[str, str] = {}
    for key, raw in record.items():
        if raw is None or isinstance(raw, dict | list):
            continue
        short = _ALIASES.get(key.lower())
        if short and short not in mapped:
            mapped[short] = _value(raw)
        elif not short:
            extra[re.sub(r"[^A-Za-z0-9_]", "_", key)[:40]] = _value(raw)
    fields = {k: v for k, v in mapped.items() if k not in ("time", "host", "user", "event")}
    fields.update(extra)
    return Event(
        time=mapped.get("time", ""),
        host=mapped.get("host", ""),
        user=mapped.get("user", ""),
        event=mapped.get("event", ""),
        fields=fields,
    )


def to_line(event: Event) -> str:
    """The event on one line: the time first, then the known fields in order, then the rest."""
    parts = [event.time] if event.time else []
    for name in ORDER[1:]:
        value = event.get(name)
        if value:
            parts.append(f"{name}={_quote(value)}")
    known = set(ORDER)
    parts += [f"{k}={_quote(v)}" for k, v in event.fields.items() if k not in known]
    return " ".join(parts)


_PAIR = re.compile(r'([A-Za-z_][\w]*)=("([^"]*)"|\S*)')


def from_line(line: str) -> Event | None:
    """Read a normalised line back - or a syslog line, or any line with key=value pairs."""
    pairs = {
        m.group(1): (m.group(3) if m.group(3) is not None else m.group(2))
        for m in _PAIR.finditer(line)
    }
    time_match = re.match(r"^\s*(\d{4}-\d{2}-\d{2}[T ][\d:.]+Z?)", line)
    syslog = _SYSLOG.match(line)
    if not pairs and not syslog:
        return None
    record: dict[str, Any] = dict(pairs)
    if time_match and "time" not in record:
        record["time"] = time_match.group(1)
    if syslog and not pairs.get("host"):
        record.setdefault("time", syslog.group("time"))
        record.setdefault("host", syslog.group("host"))
        record.setdefault("service", syslog.group("program"))
        record.setdefault("message", syslog.group("message"))
    event = normalise(record)
    return event if (event.time or event.host or event.user or event.event) else None


_SYSLOG = re.compile(
    r"^(?P<time>[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s(?P<host>[\w.-]+)\s"
    r"(?P<program>[\w./-]+)(?:\[\d+\])?:\s(?P<message>.*)$"
)


_DTD = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_SYSTEM_FIELDS = ("EventID", "Computer", "Channel", "Provider")


def _strip(tag: str) -> str:
    return tag.split("}", 1)[-1]


def events_from_xml(text: str) -> list[Event]:
    """A Windows / Sysmon export: <Event><System>...</System><EventData><Data Name=...>."""
    if _DTD.search(text):
        raise ValueError("an XML event export with a DTD or entity declaration is refused")
    root = ElementTree.fromstring(text)  # noqa: S314 - DTDs and entities are refused above
    events: list[Event] = []
    for node in root.iter():
        if _strip(node.tag) != "Event":
            continue
        record: dict[str, Any] = {}
        for child in node.iter():
            tag = _strip(child.tag)
            if tag == "TimeCreated":
                record["TimeCreated"] = child.attrib.get("SystemTime", "")
            elif tag == "Data" and child.attrib.get("Name"):
                record[child.attrib["Name"]] = child.text or ""
            elif tag in _SYSTEM_FIELDS and (child.text or "").strip():
                record[tag] = child.text
        events.append(normalise(record))
    return events


def events_from_json(text: str) -> list[Event] | None:
    """A JSON array of event objects, or JSON Lines. None when it is neither."""
    stripped = text.lstrip()
    try:
        if stripped.startswith("["):
            data = json.loads(text)
            if isinstance(data, list) and data and all(isinstance(d, dict) for d in data):
                return [normalise(d) for d in data]
            return None
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    except (ValueError, TypeError):
        return None
    if records and all(isinstance(r, dict) for r in records):
        return [normalise(r) for r in records]
    return None


def sort_key(event: Event) -> str:
    """ISO times sort as text; anything else sorts after them, in file order."""
    try:
        return datetime.fromisoformat(event.time.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return "~" + event.time
