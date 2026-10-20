"""MITRE ATT&CK mapping and the attack path (Phase 53, decision D14).

**Mapping is by rule, not by model.** `.agent/config/attack_rules.yaml` names a technique and the
event fields that indicate it; a rule matching an event yields a mapping that lists what matched and
the lines it matched on. Techniques come from the vendored ATT&CK v15.1 extract (`.agent/attack/`,
produced from the official STIX bundle by `scripts/vendor_attack.py`), so an id that does not exist
cannot be reported. Every mapping needs an analyst's validation, and a finding citing a mapped event
needs review (Phase 50). Model-suggested techniques are not built: they would be labelled `model`,
and a rule set an analyst can read was the priority.

**The attack path keeps two kinds of edge apart.** OBSERVED edges are the relations the events
state (Phase 52). INFERRED edges are concluded from observed ones by two narrow rules, each with its
reason:

- a file created on a host whose name is the last path segment of a URL the host's decoded command
  fetched from -> the URL DELIVERED the file;
- an account's remote logons to two hosts in time order -> the account MOVED_TO the second, with the
  caveat that the source address is not known to be the first host.

An inferred edge is never placed among the observed ones; a test holds the invariant.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from pydantic import Field

from app.core.agent_config import AgentConfigError, load_yaml
from app.core.config import get_settings
from app.cyber.sigma import load_sigma
from app.schemas.common import JarvisModel
from app.schemas.cyber import (
    AttackPath,
    CyberAnalysis,
    CyberEvent,
    PathEdge,
    TechniqueMapping,
)
from app.schemas.knowledge import (
    EntityType,
    GraphLink,
    GraphLinkKind,
    GraphNode,
    GraphNodeKind,
    KnowledgeGraphView,
)


class Technique(JarvisModel):
    id: str
    name: str
    tactics: list[str] = Field(default_factory=list)
    subtechnique: bool = False
    url: str = ""


class Catalogue(JarvisModel):
    version: str
    bundle_sha256: str
    source: str
    techniques: dict[str, Technique]


class Condition(JarvisModel):
    field: str
    regex: str


class Rule(JarvisModel):
    technique: str
    why: str
    all: list[Condition]


def _agent_dir() -> str:
    return str(get_settings().agent_dir)


def get_catalogue() -> Catalogue | None:
    return _catalogue(_agent_dir())


@lru_cache
def _catalogue(agent_dir: str) -> Catalogue | None:
    path = Path(agent_dir) / "attack" / "enterprise-attack.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Catalogue(
        version=raw["version"],
        bundle_sha256=raw["bundle_sha256"],
        source=raw["source"],
        techniques={t["id"]: Technique.model_validate(t) for t in raw["techniques"]},
    )


def get_rules() -> list[Rule]:
    return _rules(_agent_dir())


@lru_cache
def _rules(agent_dir: str) -> list[Rule]:
    if not (Path(agent_dir) / "config" / "attack_rules.yaml").exists():
        return []
    rules = [Rule.model_validate(r) for r in load_yaml("attack_rules.yaml").get("rules", [])]
    # Phase B5: Sigma detections, converted to the same rules and checked the same way.
    rules += [Rule.model_validate(r) for r in load_sigma(Path(agent_dir) / "attack" / "sigma")]
    catalogue = _catalogue(agent_dir)
    for rule in rules:
        if catalogue is not None and rule.technique not in catalogue.techniques:
            raise AgentConfigError(f"attack_rules.yaml names {rule.technique}, not in ATT&CK")
        for condition in rule.all:
            try:
                re.compile(condition.regex)
            except re.error as exc:
                raise AgentConfigError(f"attack rule {rule.technique}: {exc}") from exc
    return rules


def _value(event: CyberEvent, field: str) -> str:
    if field == "decoded":
        from app.cyber.analysis import decode_powershell

        return decode_powershell(event.fields.get("cmd", ""))
    if field == "event":
        return event.event
    if field in ("host", "user"):
        return event.host if field == "host" else event.user
    return event.fields.get(field, "")


def map_techniques(events: list[CyberEvent]) -> list[TechniqueMapping]:
    catalogue = get_catalogue()
    if catalogue is None:
        return []
    found: dict[str, TechniqueMapping] = {}
    for rule in get_rules():
        technique = catalogue.techniques[rule.technique]
        for event in events:
            values = [_value(event, c.field) for c in rule.all]
            if not all(
                v and re.search(c.regex, v, re.IGNORECASE)
                for v, c in zip(values, rule.all, strict=True)
            ):
                continue
            mapping = found.setdefault(
                rule.technique,
                TechniqueMapping(
                    technique_id=technique.id,
                    name=technique.name,
                    tactics=technique.tactics,
                    url=technique.url,
                    rule=rule.why,
                    first_seen=event.time,
                ),
            )
            for condition, value in zip(rule.all, values, strict=True):
                shown = f"{condition.field}={value[:120]}"
                if shown not in mapping.indicators:
                    mapping.indicators.append(shown)
            if event.locator not in mapping.evidence:
                mapping.evidence.append(event.locator)
            if event.host and event.host not in mapping.hosts:
                mapping.hosts.append(event.host)
    return sorted(found.values(), key=lambda m: (m.first_seen, m.technique_id))


def _url_file(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].lower() if "/" in url else ""


def attack_path(
    analysis: CyberAnalysis, events: list[CyberEvent], mappings: list[TechniqueMapping]
) -> AttackPath:
    by_locator: dict[str, list[str]] = {}
    for mapping in mappings:
        for locator in mapping.evidence:
            by_locator.setdefault(locator, []).append(mapping.technique_id)

    def techniques(sources: list[str]) -> list[str]:
        return sorted({t for s in sources for t in by_locator.get(s, [])})

    observed = [
        PathEdge(
            kind="OBSERVED",
            subject=r.subject,
            predicate=r.predicate,
            object=r.object,
            sources=list(r.sources),
            techniques=techniques(r.sources),
            time=r.first_seen,
        )
        for r in analysis.relations
    ]

    inferred: list[PathEdge] = []
    # A URL a decoded command fetched, and a file of that name created on the same host after it.
    urls = [
        (s.value, src)
        for s in analysis.indicators
        if s.kind == "url" and "decoded from -EncodedCommand" in s.via
        for src in s.sources
    ]
    for url, source in urls:
        name = _url_file(url)
        origin = next((e for e in events if e.locator == source), None)
        if not name or origin is None:
            continue
        for event in events:
            target = event.fields.get("TargetFilename", "")
            if (
                target
                and event.host == origin.host
                and target.replace("\\", "/").rsplit("/", 1)[-1].lower() == name
                and event.time >= origin.time
            ):
                inferred.append(
                    PathEdge(
                        kind="INFERRED",
                        subject=f"url:{url}",
                        predicate="DELIVERED",
                        object=f"file:{target}",
                        sources=[source, event.locator],
                        reason=(
                            f"the decoded command fetched {url} at {origin.time}; a file named "
                            f"{name} was created on {event.host} at {event.time}"
                        ),
                        techniques=techniques([source, event.locator]),
                        time=event.time,
                    )
                )
    # An account's remote logons in time order: a hop from each host to the next.
    remote = [
        e
        for e in events
        if e.event == "4624" and e.fields.get("logon_type") in ("3", "10") and e.user and e.host
    ]
    by_account: dict[str, list[CyberEvent]] = {}
    for event in remote:
        by_account.setdefault(event.user.lower(), []).append(event)
    for account, logons in by_account.items():
        for first, second in pairwise(logons):
            if first.host.lower() == second.host.lower():
                continue
            source_ip = second.fields.get("src_ip", "")
            inferred.append(
                PathEdge(
                    kind="INFERRED",
                    subject=f"host:{first.host.lower()}",
                    predicate="MOVED_TO",
                    object=f"host:{second.host.lower()}",
                    sources=[first.locator, second.locator],
                    reason=(
                        f"{account} logged on remotely to {first.host} at {first.time}, then to "
                        f"{second.host} at {second.time}"
                        + (
                            f"; the second logon came from {source_ip}, not known to be "
                            f"{first.host}"
                            if source_ip
                            else ""
                        )
                    ),
                    techniques=techniques([first.locator, second.locator]),
                    time=second.time,
                )
            )
    return AttackPath(observed=observed, inferred=sorted(inferred, key=lambda e: e.time))


def attach_attack(analysis: CyberAnalysis, events: list[CyberEvent]) -> CyberAnalysis:
    """The analysis with its techniques and attack path (Phase 53)."""
    if not events:
        return analysis
    mappings = map_techniques(events)
    catalogue = get_catalogue()
    analysis.techniques = mappings
    analysis.attack_path = attack_path(analysis, events, mappings)
    analysis.attack_version = f"ATT&CK v{catalogue.version}" if catalogue else ""
    return analysis


def mapped_locators(analysis: CyberAnalysis) -> set[str]:
    """Every line a technique mapping rests on: a finding citing one needs review (Phase 50)."""
    return {locator for mapping in analysis.techniques for locator in mapping.evidence}


def attack_graph(run_id: str, analysis: CyberAnalysis) -> KnowledgeGraphView:
    """The attack path as the 3D explorer draws it: hosts, accounts, processes and the rest as
    entities; observed steps as RELATES; inferred steps as INFERRED, labelled with their reason;
    each mapped technique as a node joined to the hosts it was seen on (MAPS_TO)."""
    nodes: dict[str, GraphNode] = {}

    def node(key: str) -> str:
        kind, _, name = key.partition(":")
        if key not in nodes:
            nodes[key] = GraphNode(
                id=key,
                kind=GraphNodeKind.ENTITY,
                label=f"{kind} {name}"[:120] or key,
                entity_type=EntityType.PERSON if kind == "account" else EntityType.OTHER,
                status=kind,
            )
        return key

    links: list[GraphLink] = []
    for edge in analysis.attack_path.observed:
        links.append(
            GraphLink(
                source=node(edge.subject),
                target=node(edge.object),
                kind=GraphLinkKind.RELATES,
                label=edge.predicate.replace("_", " ").lower(),
            )
        )
    for edge in analysis.attack_path.inferred:
        links.append(
            GraphLink(
                source=node(edge.subject),
                target=node(edge.object),
                kind=GraphLinkKind.INFERRED,
                label=f"inferred {edge.predicate.replace('_', ' ').lower()}: {edge.reason}"[:300],
            )
        )
    for mapping in analysis.techniques:
        key = f"technique:{mapping.technique_id}"
        nodes[key] = GraphNode(
            id=key,
            kind=GraphNodeKind.ENTITY,
            label=f"{mapping.technique_id} {mapping.name}",
            entity_type=EntityType.OTHER,
            status="technique (needs validation)",
            source=", ".join(mapping.evidence),
        )
        for host in mapping.hosts:
            links.append(
                GraphLink(
                    source=key,
                    target=node(f"host:{host.lower()}"),
                    kind=GraphLinkKind.MAPS_TO,
                    label=f"rule: {mapping.rule}",
                )
            )
    return KnowledgeGraphView(
        run_id=run_id, store="attack-path", nodes=list(nodes.values()), links=links
    )


# A question about an attack: whether something malicious happened, a compromise, an intrusion.
_ATTACK_QUESTION = re.compile(
    r"\b(malicious|compromis\w*|attack\w*|intrusion|breach\w*|threat|exfiltrat\w*|"
    r"backdoor|malware|ransomware|lateral movement)\b",
    re.IGNORECASE,
)


def asks_about_attack(objective: str) -> bool:
    return bool(_ATTACK_QUESTION.search(objective))


def quiet_logs(documents: dict[str, str] | None) -> bool:
    """Security logs in which no detection rule flagged a single event (Phase 54, BUG-038).

    Asked whether such logs show an attack, a description of ordinary activity - a backup finished,
    an administrator upgraded packages - is not an answer, and reasoning discards it with that
    reason. The cost is stated: an attack no rule covers is then reported as nothing; the held-out
    ATT&CK fixture (recall 0.400) is the measure of how much that can be.
    """
    if not documents:
        return False
    from app.cyber.analysis import analyse

    analysis = analyse(documents)
    return analysis.events > 0 and not analysis.techniques
