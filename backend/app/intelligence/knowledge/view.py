"""A run's knowledge as nodes and links (Phase 31), for the API and the 3D explorer.

Built from the `KnowledgeBase` protocol, so it reads the same from Neo4j and from memory, plus the
run's findings for `CITES` links. Node ids are stable and self-describing:

| Kind | Id | Example |
|---|---|---|
| entity | its `entity_id` | `ENT-004` |
| claim | its `claim_id` | `CLM-012` |
| document | `DOC:` + document id | `DOC:report.pdf` |
| finding | its `finding_id` | `F-001` |

**Entities are parents and claims are their sub-nodes** (`GraphNode.parent`): what the 3D view
reveals when an entity is expanded. A contradiction is a `CONFLICTS_WITH` link between the first
claim of each pair of sides, the same edge the Neo4j store writes.
"""

from __future__ import annotations

from app.intelligence.knowledge.base import KnowledgeBase, clamp_depth
from app.schemas.finding import Finding
from app.schemas.knowledge import (
    ClaimConflict,
    FindingTrail,
    GraphLink,
    GraphLinkKind,
    GraphNode,
    GraphNodeKind,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeGraphView,
    NodeDetail,
)

DOC_PREFIX = "DOC:"
MAX_LABEL = 80


def document_node_id(document_id: str) -> str:
    return f"{DOC_PREFIX}{document_id}"


def _document_of(source: str) -> str:
    return source.rpartition(":")[0] or source


def _short(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1] + "…"


def _resolved_sources(finding: Finding) -> list[str]:
    return [ref.as_ref() for ref in finding.evidence if ref.is_resolved]


def _status(finding: Finding) -> str:
    return finding.verification.status.value if finding.verification else ""


def _conflict_links(conflicts: list[ClaimConflict], keep: set[str]) -> list[GraphLink]:
    links: list[GraphLink] = []
    for conflict in conflicts:
        heads = [side.claim_ids[0] for side in conflict.sides]
        for n, a in enumerate(heads):
            for b in heads[n + 1 :]:
                if a in keep and b in keep:
                    links.append(
                        GraphLink(
                            source=a,
                            target=b,
                            kind=GraphLinkKind.CONFLICTS_WITH,
                            label=conflict.attribute,
                        )
                    )
    return links


def _entity_node(
    entity: KnowledgeEntity, claims: list[KnowledgeClaim], conflicts: list[ClaimConflict]
) -> GraphNode:
    return GraphNode(
        id=entity.entity_id,
        kind=GraphNodeKind.ENTITY,
        label=entity.name,
        entity_type=entity.entity_type,
        claim_count=sum(1 for c in claims if c.entity_id == entity.entity_id),
        conflict_count=sum(1 for k in conflicts if k.entity_id == entity.entity_id),
    )


def _claim_node(claim: KnowledgeClaim, in_conflict: set[str]) -> GraphNode:
    return GraphNode(
        id=claim.claim_id,
        kind=GraphNodeKind.CLAIM,
        label=_short(f"{claim.attribute} = {claim.value}"),
        parent=claim.entity_id,
        conflict_count=1 if claim.claim_id in in_conflict else 0,
        grounded=claim.grounded,
        source=claim.source,
    )


async def build_view(
    base: KnowledgeBase,
    run_id: str,
    findings: list[Finding],
    *,
    focus: str | None = None,
    depth: int = 2,
) -> KnowledgeGraphView:
    """The whole knowledge graph, or the neighbourhood of `focus` within `depth` hops."""
    entities = await base.entities()
    relationships = await base.relationships()
    claims = await base.claims()
    conflicts = await base.conflicts()

    hops = clamp_depth(depth)
    if focus is not None:
        network = await base.network(focus, hops)
        kept = {n.entity_id for n in network.nodes} if network else set()
        entities = [e for e in entities if e.entity_id in kept]
        claims = [c for c in claims if c.entity_id in kept]
        relationships = [r for r in relationships if r.subject_id in kept and r.object_id in kept]

    claim_ids = {c.claim_id for c in claims}
    in_conflict = {claim_id for k in conflicts for side in k.sides for claim_id in side.claim_ids}
    documents = sorted(
        {c.document_id for c in claims} | {_document_of(s) for e in entities for s in e.sources}
    )

    nodes = [_entity_node(e, claims, conflicts) for e in entities]
    nodes += [_claim_node(c, in_conflict) for c in claims]
    nodes += [
        GraphNode(id=document_node_id(d), kind=GraphNodeKind.DOCUMENT, label=d) for d in documents
    ]

    links = [
        GraphLink(
            source=r.subject_id, target=r.object_id, kind=GraphLinkKind.RELATES, label=r.predicate
        )
        for r in relationships
    ]
    links += [
        GraphLink(source=c.entity_id, target=c.claim_id, kind=GraphLinkKind.HAS_CLAIM)
        for c in claims
    ]
    links += [
        GraphLink(
            source=c.claim_id, target=document_node_id(c.document_id), kind=GraphLinkKind.CITED_IN
        )
        for c in claims
    ]
    links += [
        GraphLink(source=e.entity_id, target=document_node_id(d), kind=GraphLinkKind.MENTIONED_IN)
        for e in entities
        for d in sorted({_document_of(s) for s in e.sources})
    ]
    links += _conflict_links(conflicts, claim_ids)

    by_source: dict[str, list[str]] = {}
    for claim in claims:
        by_source.setdefault(claim.source, []).append(claim.claim_id)
    for finding in findings:
        cited = [cid for s in _resolved_sources(finding) for cid in by_source.get(s, [])]
        cited_docs = sorted({_document_of(s) for s in _resolved_sources(finding)} & set(documents))
        if focus is not None and not cited:
            continue
        nodes.append(
            GraphNode(
                id=finding.finding_id,
                kind=GraphNodeKind.FINDING,
                label=_short(finding.claim),
                status=_status(finding),
            )
        )
        links += [
            GraphLink(source=finding.finding_id, target=cid, kind=GraphLinkKind.CITES)
            for cid in dict.fromkeys(cited)
        ]
        links += [
            GraphLink(
                source=finding.finding_id, target=document_node_id(d), kind=GraphLinkKind.CITES
            )
            for d in cited_docs
        ]

    return KnowledgeGraphView(
        run_id=run_id,
        store=base.store,
        focus=focus,
        depth=hops if focus is not None else 0,
        nodes=nodes,
        links=links,
    )


async def finding_trail(base: KnowledgeBase, finding: Finding) -> FindingTrail:
    """The claims, documents and entities a finding rests on, and the links between them."""
    sources = _resolved_sources(finding)
    claims = [c for c in await base.claims() if c.source in sources]
    matched = {c.source for c in claims}
    documents = sorted({_document_of(s) for s in sources})
    entities = sorted({c.entity_id for c in claims})
    claim_ids = {c.claim_id for c in claims}

    links = [
        GraphLink(source=finding.finding_id, target=c.claim_id, kind=GraphLinkKind.CITES)
        for c in claims
    ]
    links += [
        GraphLink(source=finding.finding_id, target=document_node_id(d), kind=GraphLinkKind.CITES)
        for d in documents
    ]
    links += [
        GraphLink(source=c.entity_id, target=c.claim_id, kind=GraphLinkKind.HAS_CLAIM)
        for c in claims
    ]
    links += [
        GraphLink(
            source=c.claim_id, target=document_node_id(c.document_id), kind=GraphLinkKind.CITED_IN
        )
        for c in claims
    ]
    links += _conflict_links(await base.conflicts(), claim_ids)

    return FindingTrail(
        finding_id=finding.finding_id,
        claim=finding.claim,
        status=_status(finding),
        node_ids=[
            finding.finding_id,
            *sorted(claim_ids),
            *entities,
            *(document_node_id(d) for d in documents),
        ],
        links=links,
        unmatched_sources=[s for s in sources if s not in matched],
    )


async def node_detail(
    base: KnowledgeBase, node_id: str, findings: list[Finding]
) -> NodeDetail | None:
    """What the pop-up shows for one node. None if no such node exists."""
    conflicts = await base.conflicts()

    if node_id.startswith(DOC_PREFIX):
        document = node_id[len(DOC_PREFIX) :]
        claims = [c for c in await base.claims() if c.document_id == document]
        entities = [
            e for e in await base.entities() if any(_document_of(s) == document for s in e.sources)
        ]
        if not claims and not entities:
            return None
        return NodeDetail(
            node=GraphNode(id=node_id, kind=GraphNodeKind.DOCUMENT, label=document),
            claims=claims,
            entities=entities,
            conflicts=[
                k
                for k in conflicts
                if any(s for side in k.sides for s in side.sources if _document_of(s) == document)
            ],
        )

    finding = next((f for f in findings if f.finding_id == node_id), None)
    if finding is not None:
        trail = await finding_trail(base, finding)
        claims = [c for c in await base.claims() if c.claim_id in trail.node_ids]
        return NodeDetail(
            node=GraphNode(
                id=node_id,
                kind=GraphNodeKind.FINDING,
                label=_short(finding.claim),
                status=_status(finding),
            ),
            claims=claims,
            documents=sorted({_document_of(s) for s in _resolved_sources(finding)}),
            finding_claim=finding.claim,
            finding_status=_status(finding),
        )

    claim = await base.claim(node_id)
    if claim is not None:
        in_conflict = {cid for k in conflicts for side in k.sides for cid in side.claim_ids}
        owner = next((e for e in await base.entities() if e.entity_id == claim.entity_id), None)
        return NodeDetail(
            node=_claim_node(claim, in_conflict),
            entity=owner,
            claims=[claim],
            conflicts=[k for k in conflicts if any(claim.claim_id in s.claim_ids for s in k.sides)],
            documents=[claim.document_id],
        )

    entity = next((e for e in await base.entities() if e.entity_id == node_id), None)
    if entity is None:
        return None
    claims = await base.claims(entity.entity_id)
    entity_conflicts = await base.conflicts(entity.entity_id)
    return NodeDetail(
        node=_entity_node(entity, claims, entity_conflicts),
        entity=entity,
        claims=claims,
        conflicts=entity_conflicts,
        relationships=await base.relationships(entity.entity_id),
        documents=sorted(
            {_document_of(s) for s in entity.sources} | {c.document_id for c in claims}
        ),
    )
