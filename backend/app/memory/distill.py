"""What a finished run contributes to memory (Phase 33). Pure: no store, no I/O.

Everything here is derived from the `MissionResult`, so what is remembered about a run can be
recomputed from the run, and the stores only hold it.

**Only verified findings become facts.** Member 4 had no gate: any fact added was kept, with
`confidence=1.0`. Distilling an unverified claim into durable memory would make a hallucination
permanent, so a knowledge claim or relationship becomes a fact only when a verified finding cites
the line it was read from - the same match the evidence trail uses (`view.finding_trail`).
Episodes are the opposite: every finding is logged, rejected ones included, with its status.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from app.intelligence.knowledge.store import normalize_attribute, normalize_name
from app.orchestration.mission import MissionResult
from app.schemas.finding import Finding, FindingClassification
from app.schemas.knowledge import KnowledgeEntity, KnowledgeSnapshot
from app.schemas.memory import (
    ArchivedInvestigation,
    Episode,
    Fact,
    FactKind,
    FactSupport,
    KnownEntity,
    MemoryRecord,
    WorkingMemorySnapshot,
)

_SPACES = re.compile(r"\s+")


def working_snapshot(
    result: MissionResult, started_at: datetime | None = None
) -> WorkingMemorySnapshot:
    """Member 4's working memory at the end of a run, read off the result.

    Plan steps include tasks the replanning loop inserted (`result.plan` is the executed graph).
    Evidence is a count, as in Member 4's `snapshot()`: here, the observations the run made.
    """
    findings = result.findings
    return WorkingMemorySnapshot(
        investigation_id=result.run_id,
        objective=result.objective.text,
        plan_steps=[t.description for t in result.plan.tasks] if result.plan else [],
        evidence_count=len(result.observations),
        hypotheses=[
            f.claim for f in findings if f.classification is FindingClassification.HYPOTHESIS
        ],
        findings=[
            f.claim for f in findings if f.classification is not FindingClassification.HYPOTHESIS
        ],
        started_at=started_at,
    )


def episodes(result: MissionResult) -> list[Episode]:
    """One episode per finding, whatever its verification status."""
    return [
        Episode(
            episode_id=f"{result.run_id}:{f.finding_id}",
            run_id=result.run_id,
            objective=result.objective.text,
            claim=f.claim,
            sources=_resolved_sources(f),
            verification_status=f.verification.status.value if f.verification else "UNVERIFIED",
            created_at=f.created_at,
        )
        for f in result.findings
    ]


def known_entities(run_id: str, snapshot: KnowledgeSnapshot) -> list[KnownEntity]:
    """The run's entities, keyed by normalised name, ready to merge with other runs'."""
    merged: dict[str, KnownEntity] = {}
    for entity in snapshot.entities:
        key = normalize_name(entity.name)
        if not key:
            continue
        known = merged.get(key)
        if known is None:
            merged[key] = KnownEntity(
                key=key,
                name=entity.name,
                entity_types=[entity.entity_type],
                aliases=sorted(set(entity.aliases)),
                runs=[run_id],
            )
            continue
        if entity.entity_type not in known.entity_types:
            known.entity_types.append(entity.entity_type)
        known.aliases = sorted(set(known.aliases) | set(entity.aliases) | {entity.name})
    return list(merged.values())


def verified_facts(run_id: str, snapshot: KnowledgeSnapshot, findings: list[Finding]) -> list[Fact]:
    """Claims and relationships cited by a verified finding, as subject-predicate-object facts."""
    cited = {source for f in findings if f.is_verified for source in _resolved_sources(f)}
    if not cited:
        return []
    by_id: dict[str, KnowledgeEntity] = {e.entity_id: e for e in snapshot.entities}
    facts: dict[str, Fact] = {}

    def add(kind: FactKind, subject: str, predicate: str, obj: str, source: str) -> None:
        fact = make_fact(kind, subject, predicate, obj)
        existing = facts.setdefault(fact.fact_id, fact)
        support = FactSupport(run_id=run_id, source=source)
        if support not in existing.support:
            existing.support.append(support)

    for claim in snapshot.claims:
        entity = by_id.get(claim.entity_id)
        if claim.grounded and claim.source in cited and entity is not None:
            add(FactKind.ATTRIBUTE, entity.name, claim.attribute, claim.value, claim.source)
    for rel in snapshot.relationships:
        subject, obj = by_id.get(rel.subject_id), by_id.get(rel.object_id)
        if rel.source in cited and subject is not None and obj is not None:
            add(FactKind.RELATION, subject.name, rel.predicate, obj.name, rel.source)
    return list(facts.values())


def make_fact(kind: FactKind, subject: str, predicate: str, obj: str) -> Fact:
    """A fact with a stable id: the same statement from two runs is one fact."""
    subject_key = normalize_name(subject)
    predicate_key = normalize_attribute(predicate)
    object_key = normalize_name(obj) if kind is FactKind.RELATION else _value_key(obj)
    digest = hashlib.sha1(  # noqa: S324 - an identifier, not a security boundary
        f"{kind.value}|{subject_key}|{predicate_key}|{object_key}".encode()
    ).hexdigest()
    return Fact(
        fact_id=f"FACT-{digest[:16]}",
        kind=kind,
        subject=subject,
        subject_key=subject_key,
        predicate=predicate_key or predicate,
        object=obj,
        object_key=object_key,
    )


def memory_record(result: MissionResult, started_at: datetime | None = None) -> MemoryRecord:
    """Everything a finished run contributes to memory."""
    snapshot = result.knowledge or KnowledgeSnapshot()
    return MemoryRecord(
        run_id=result.run_id,
        investigation=ArchivedInvestigation(
            run_id=result.run_id,
            objective=result.objective.text,
            snapshot=working_snapshot(result, started_at),
        ),
        episodes=episodes(result),
        entities=known_entities(result.run_id, snapshot),
        facts=verified_facts(result.run_id, snapshot, result.findings),
    )


def _resolved_sources(finding: Finding) -> list[str]:
    return [ref.as_ref() for ref in finding.evidence if ref.is_resolved]


def _value_key(value: str) -> str:
    return _SPACES.sub(" ", value.casefold()).strip()
