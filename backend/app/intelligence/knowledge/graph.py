"""An entity's neighbourhood in the knowledge graph (K5), in memory.

Ported from Member 3's `graph.py`, which rebuilt a NetworkX `DiGraph` from SQLite on every request
and returned `ego_graph(G.to_undirected(), entity, radius=depth)`: every entity within `depth` hops
**in either direction**, and the stored (directed) edges between them. The same result here, by
breadth-first search, with no NetworkX dependency.

Phase 29 answers the same query from Neo4j. This in-memory version is the fallback when Neo4j is
not running, and the reference both implementations are tested against.
"""

from __future__ import annotations

from app.schemas.knowledge import (
    EntityNetwork,
    KnowledgeEntity,
    KnowledgeRelationship,
    NetworkEdge,
    NetworkNode,
)


def neighbourhood(
    center_id: str,
    depth: int,
    entities: list[KnowledgeEntity],
    relationships: list[KnowledgeRelationship],
) -> EntityNetwork | None:
    """Entities within `depth` hops of `center_id`, ignoring direction. None if it is unknown."""
    by_id = {e.entity_id: e for e in entities}
    if center_id not in by_id:
        return None

    adjacent: dict[str, set[str]] = {}
    for rel in relationships:
        adjacent.setdefault(rel.subject_id, set()).add(rel.object_id)
        adjacent.setdefault(rel.object_id, set()).add(rel.subject_id)

    reached = {center_id}
    frontier = {center_id}
    # Bounded by `depth`, and by the finite entity set: each pass only adds unseen entities.
    for _ in range(max(0, depth)):
        frontier = {n for node in frontier for n in adjacent.get(node, set())} - reached
        if not frontier:
            break
        reached |= frontier

    nodes = [
        NetworkNode(entity_id=e.entity_id, name=e.name, entity_type=e.entity_type)
        for e in entities
        if e.entity_id in reached
    ]
    edges = [
        NetworkEdge(
            from_id=rel.subject_id, to_id=rel.object_id, predicate=rel.predicate, source=rel.source
        )
        for rel in relationships
        if rel.subject_id in reached and rel.object_id in reached
    ]
    return EntityNetwork(center_id=center_id, depth=depth, nodes=nodes, edges=edges)
