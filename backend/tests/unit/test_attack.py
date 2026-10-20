"""Phase 53: MITRE ATT&CK mapping and the attack path.

Techniques come from the vendored ATT&CK v15.1 extract and are mapped by declared rules, each with
what matched and the lines it matched on, each needing an analyst. The attack path keeps observed
and inferred edges apart, and no inferred edge is ever shown as observed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry
from app.core.config import get_settings
from app.cyber.analysis import analyse
from app.cyber.attack import attack_graph, get_catalogue, get_rules
from app.cyber.eventlog import from_line, normalise, to_line
from app.evaluation.attack import run_attack_benchmark
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.knowledge import GraphLinkKind
from app.schemas.objective import Objective
from app.schemas.verification import VerificationResult, VerificationStatus
from app.tools.formats import parse

FIXTURES = get_settings().agent_dir / "fixtures" / "documents"


def _analysis(name: str):  # type: ignore[no-untyped-def]
    return analyse({name: parse(FIXTURES / name).text})


# --- the catalogue and the rules ------------------------------------------------------------------


def test_the_catalogue_is_the_pinned_official_extract() -> None:
    catalogue = get_catalogue()
    assert catalogue is not None and catalogue.version == "15.1"
    assert len(catalogue.bundle_sha256) == 64
    assert catalogue.techniques["T1059.001"].name == "PowerShell"
    assert catalogue.techniques["T1059.001"].tactics == ["execution"]


def test_every_rule_names_a_technique_the_catalogue_holds() -> None:
    catalogue = get_catalogue()
    assert catalogue is not None
    rules = get_rules()
    assert rules and all(r.technique in catalogue.techniques for r in rules)


def test_the_vendoring_script_reduces_a_bundle_deterministically() -> None:
    spec = importlib.util.spec_from_file_location(
        "vendor_attack", Path(__file__).parents[2] / "scripts" / "vendor_attack.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["vendor_attack"] = module
    spec.loader.exec_module(module)
    bundle = (
        b'{"objects": ['
        b'{"type": "x-mitre-matrix", "id": "m", "tactic_refs": ["t1"]},'
        b'{"type": "x-mitre-tactic", "id": "t1", "name": "Execution", "x_mitre_shortname": '
        b'"execution", "external_references": [{"source_name": "mitre-attack", "external_id": '
        b'"TA0002"}]},'
        b'{"type": "attack-pattern", "id": "a", "name": "PowerShell", "x_mitre_is_subtechnique": '
        b'true, "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": '
        b'"execution"}], "external_references": [{"source_name": "mitre-attack", "external_id": '
        b'"T1059.001", "url": "https://attack.mitre.org/techniques/T1059/001"}]},'
        b'{"type": "attack-pattern", "id": "b", "name": "Old", "revoked": true, '
        b'"external_references": [{"source_name": "mitre-attack", "external_id": "T9999"}]}'
        b"]}"
    )
    first = module.extract(bundle)
    assert first == module.extract(bundle)
    assert [t["id"] for t in first["techniques"]] == ["T1059.001"], "revoked ones are dropped"
    assert first["tactics"] == [{"shortname": "execution", "id": "TA0002", "name": "Execution"}]


# --- mapping --------------------------------------------------------------------------------------


def test_the_powershell_log_maps_to_its_techniques_with_their_lines() -> None:
    mappings = {m.technique_id: m for m in _analysis("cyber_ws12_security.xml").techniques}
    assert set(mappings) == {"T1059.001", "T1027", "T1105", "T1204.002", "T1071.001"}
    cradle = mappings["T1105"]
    assert cradle.evidence == ["cyber_ws12_security.xml:r2"]
    assert cradle.indicators[0].startswith("decoded=IEX (New-Object Net.WebClient)")
    assert cradle.source == "rule" and cradle.needs_validation
    assert cradle.tactics == ["command-and-control"]


def test_benign_administration_maps_to_nothing() -> None:
    assert _analysis("cyber_admin_benign.log").techniques == []


def test_a_quoted_argument_survives_normalisation() -> None:
    """`net group "Domain Admins" /domain` was cut at its first quote, and T1069.002 missed."""
    line = to_line(
        normalise({"host": "SRV-DB", "CommandLine": 'net group "Domain Admins" /domain'})
    )
    event = from_line(line)
    assert event is not None and event.fields["cmd"] == "net group 'Domain Admins' /domain"
    techniques = {m.technique_id for m in _analysis("cyber_lateral_movement.jsonl").techniques}
    assert "T1069.002" in techniques


# --- the attack path ------------------------------------------------------------------------------


def test_no_inferred_edge_is_reported_as_observed() -> None:
    for name in ("cyber_ws12_security.xml", "cyber_lateral_movement.jsonl"):
        path = _analysis(name).attack_path
        assert path.inferred, name
        assert all(e.kind == "OBSERVED" for e in path.observed)
        assert all(e.kind == "INFERRED" and e.reason for e in path.inferred)
        observed = {(e.subject, e.predicate, e.object) for e in path.observed}
        assert not observed & {(e.subject, e.predicate, e.object) for e in path.inferred}


def test_the_download_and_the_hop_are_inferred_with_their_reasons() -> None:
    [delivered] = _analysis("cyber_ws12_security.xml").attack_path.inferred
    assert (delivered.predicate, delivered.subject) == (
        "DELIVERED",
        "url:http://203.0.113.50/stage.ps1",
    )
    assert delivered.sources == ["cyber_ws12_security.xml:r2", "cyber_ws12_security.xml:r4"]
    [hop] = _analysis("cyber_lateral_movement.jsonl").attack_path.inferred
    assert (hop.subject, hop.predicate, hop.object) == ("host:srv-db", "MOVED_TO", "host:srv-file")
    assert "not known to be SRV-DB" in hop.reason
    assert hop.techniques == ["T1078"]


def test_the_3d_view_draws_inferred_steps_as_inferred() -> None:
    analysis = _analysis("cyber_lateral_movement.jsonl")
    view = attack_graph("run_0123456789ab", analysis)
    inferred = [link for link in view.links if link.kind is GraphLinkKind.INFERRED]
    assert len(inferred) == 1 and inferred[0].label.startswith("inferred moved to:")
    assert len([lk for lk in view.links if lk.kind is GraphLinkKind.RELATES]) == len(
        analysis.attack_path.observed
    )
    techniques = [n for n in view.nodes if n.id.startswith("technique:")]
    assert {n.label.split(" ")[0] for n in techniques} == {
        m.technique_id for m in analysis.techniques
    }
    assert all(n.status == "technique (needs validation)" for n in techniques)


# --- the benchmark --------------------------------------------------------------------------------


def test_the_benchmark_is_precise_and_honest_about_what_it_misses() -> None:
    report = run_attack_benchmark()
    assert report.technique_precision == 1.0
    # B5: the Sigma rules map what the held-out fixture used to miss (it is no longer held out).
    assert report.technique_recall == pytest.approx(1.0)
    assert report.held_out_recall == pytest.approx(1.0)
    held = next(c for c in report.cases if c.fixture == "cyber_persistence_held_out.jsonl")
    assert held.missed == []


# --- a finding on a mapped event needs an analyst (Phase 50) --------------------------------------


async def test_a_finding_citing_a_mapped_event_needs_review() -> None:
    texts = {"cyber_ws12_security.xml": parse(FIXTURES / "cyber_ws12_security.xml").text}
    finding = Finding(
        finding_id="F-001",
        claim="PowerShell ran an encoded download cradle.",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id="cyber_ws12_security.xml", row=2),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    record = MissionRecord(new_run_id(), Objective(text="What ran on WS-12?"), list(texts))
    record.status, record.stage, record.texts = MissionStatus.COMPLETED, Stage.DONE, texts
    record.result = MissionResult(
        run_id=record.run_id, objective=record.objective, findings=[finding]
    )
    get_registry()._missions[record.run_id] = record

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        reviews = (await c.get(f"/api/v1/missions/{record.run_id}/reviews")).json()["reviews"]
        graph = await c.get(f"/api/v1/missions/{record.run_id}/attack-graph")

    assert "it maps to a MITRE ATT&CK technique" in reviews[0]["required_because"]
    assert graph.status_code == 200 and graph.json()["store"] == "attack-path"


# --- quiet logs (Phase 54) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("objective", "about"),
    [
        ("Do these server logs show malicious activity or a compromise?", True),
        ("Was there lateral movement between the servers?", True),
        ("Investigate the PowerShell activity on WS-12.", False),
        ("When does Project Vega start?", False),
    ],
)
def test_an_attack_question_is_recognised(objective: str, about: bool) -> None:
    from app.cyber.attack import asks_about_attack

    assert asks_about_attack(objective) is about


def test_only_logs_with_no_detection_are_quiet() -> None:
    from app.cyber.attack import quiet_logs

    def documents(name: str) -> dict[str, str]:
        return {name: parse(FIXTURES / name).text}

    assert quiet_logs(documents("cyber_admin_benign.log"))
    assert not quiet_logs(documents("cyber_ws12_security.xml"))
    assert not quiet_logs({"report.txt": "The approved budget is 250,000."}), "no events at all"


async def test_reasoning_discards_descriptions_of_quiet_logs_and_says_why() -> None:
    """Measured in the 20-scenario baseline: asked whether benign logs showed a compromise, the
    agent reported a finished backup and a package upgrade."""
    import json

    from app.intelligence.reasoning.engine import DISCARD_NO_DETECTION, ReasoningEngine
    from app.llm.echo import EchoProvider
    from app.schemas.execution import Observation

    text = parse(FIXTURES / "cyber_admin_benign.log").text
    candidates = json.dumps(
        {"findings": [{"claim": "A backup completed at 01:00:01.", "citations": ["b.log:r1"]}]}
    )
    relevant = json.dumps({"verdicts": [{"index": 1, "keep": True, "reason": "x"}]})
    engine = ReasoningEngine(
        EchoProvider(responses={"reasoning": [candidates], "relevance": [relevant]})
    )
    findings = await engine.derive_findings(
        Objective(text="Do these server logs show malicious activity or a compromise?"),
        [
            Observation(
                task_id="task_001", task_type="extract_timeline", content="x", sources=["b.log:r1"]
            )
        ],
        documents={"b.log": text},
    )
    assert findings == []
    assert engine.discarded[DISCARD_NO_DETECTION] == 1
