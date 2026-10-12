"""Cyber investigation data (Phase 52): events, indicators, entities, relations, timelines.

Everything here is read from the logs without a model, and every item cites the lines it came from.
Relations are observed - stated by one or more events. Inferred edges arrive with the attack path in
Phase 53, named as inferred.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import JarvisModel


class CyberEvent(JarvisModel):
    locator: str
    time: str = ""
    host: str = ""
    user: str = ""
    event: str = ""
    summary: str = ""
    fields: dict[str, str] = Field(default_factory=dict)


class IndicatorSighting(JarvisModel):
    kind: str
    value: str
    # Written defanged in the log (hxxp, [.]), reported refanged.
    defanged: bool = False
    sources: list[str] = Field(default_factory=list)
    # How it was found when not on the line as written: "decoded from -EncodedCommand".
    via: list[str] = Field(default_factory=list)


class CyberEntity(JarvisModel):
    kind: str  # host, account, process, ipv4, domain, service, script
    name: str
    sources: list[str] = Field(default_factory=list)


class CyberRelation(JarvisModel):
    subject: str  # "kind:name"
    predicate: str
    object: str
    # Observed: the events that state it. (Phase 53's inferred edges are a separate kind.)
    sources: list[str] = Field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    detail: str = ""


class TimelineItem(JarvisModel):
    time: str
    locator: str
    summary: str


class DecodedCommand(JarvisModel):
    locator: str
    host: str = ""
    user: str = ""
    script: str


class SimilarCase(JarvisModel):
    """Another case sharing indicators with this one (D19): context, never evidence."""

    case_id: str
    run_id: str
    shared: list[str] = Field(default_factory=list)


class TechniqueMapping(JarvisModel):
    """One ATT&CK technique a rule matched (Phase 53): evidence for an analyst, never a verdict."""

    technique_id: str
    name: str
    tactics: list[str] = Field(default_factory=list)
    url: str = ""
    # Which rule, in words, and that it came from a rule (model suggestions would say "model").
    rule: str
    source: str = "rule"
    indicators: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    first_seen: str = ""
    needs_validation: bool = True


class PathEdge(JarvisModel):
    """One step of an attack path. OBSERVED: events state it. INFERRED: a rule concluded it from
    observed steps, and says how - never shown as observed."""

    kind: str  # OBSERVED | INFERRED
    subject: str
    predicate: str
    object: str
    sources: list[str] = Field(default_factory=list)
    reason: str = ""
    techniques: list[str] = Field(default_factory=list)
    time: str = ""


class AttackPath(JarvisModel):
    observed: list[PathEdge] = Field(default_factory=list)
    inferred: list[PathEdge] = Field(default_factory=list)


class CyberAnalysis(JarvisModel):
    events: int = 0
    documents: list[str] = Field(default_factory=list)
    indicators: list[IndicatorSighting] = Field(default_factory=list)
    entities: list[CyberEntity] = Field(default_factory=list)
    relations: list[CyberRelation] = Field(default_factory=list)
    host_timelines: dict[str, list[TimelineItem]] = Field(default_factory=dict)
    account_timelines: dict[str, list[TimelineItem]] = Field(default_factory=dict)
    decoded_commands: list[DecodedCommand] = Field(default_factory=list)
    # Opt-in per case (D19). Labelled context: nothing here can be cited by a finding.
    similar_cases: list[SimilarCase] = Field(default_factory=list)
    recall: str = "off"
    # Phase 53: ATT&CK techniques the rules matched, and the attack path.
    techniques: list[TechniqueMapping] = Field(default_factory=list)
    attack_path: AttackPath = Field(default_factory=AttackPath)
    attack_version: str = ""
