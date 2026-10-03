"""Choosing where a run's knowledge graph lives (Phase 29, ADR-010).

`GRAPH_STORE=neo4j` (the default) writes each run's graph to Neo4j and answers from there;
`GRAPH_STORE=memory` keeps it in the process. **Neo4j is optional, and it never fails a run.** It
follows the same two rules as run persistence (`app/api/persistence.py`):

- **Availability is probed once per process.** When Neo4j is unreachable the run uses the in-memory
  store, and the log says so once (`graph_store_degraded`), not once per run.
- **A failed write degrades, it does not raise.** The run keeps its knowledge in memory and the
  failure is logged. Losing the graph's copy in Neo4j is bad; losing the investigation to save it
  would be worse.

The Neo4j async driver belongs to the event loop that created it. The API runs one loop for its
lifetime, while the CLI and the test suite start several, so the store is cached per loop.
"""

from __future__ import annotations

import asyncio

from app.core.config import GraphStoreName, get_settings
from app.core.logging import get_logger
from app.integrations.neo4j_store import Neo4jGraphStore
from app.intelligence.knowledge.base import InMemoryKnowledgeBase, KnowledgeBase
from app.schemas.knowledge import KnowledgeSnapshot

log = get_logger(__name__)

# Probed once per process: None until probed, then whether Neo4j answered.
_available: bool | None = None
_stores: dict[int, Neo4jGraphStore] = {}


def _connect() -> Neo4jGraphStore:
    settings = get_settings()
    return Neo4jGraphStore.connect(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password,
        settings.neo4j_database,
    )


async def get_graph_store() -> Neo4jGraphStore | None:
    """The Neo4j store for this event loop, or None when it is off or unreachable."""
    global _available
    if get_settings().graph_store is not GraphStoreName.NEO4J:
        return None

    loop = id(asyncio.get_running_loop())
    store = _stores.get(loop)
    if store is None:
        store = _connect()
        _stores[loop] = store

    if _available is None:
        _available = await store.available()
        if _available:
            log.info("graph_store_enabled", store="neo4j", uri=get_settings().neo4j_uri)
        else:
            log.warning(
                "graph_store_degraded",
                reason="Neo4j is not reachable; knowledge graphs are kept in memory",
                uri=get_settings().neo4j_uri,
            )
    return store if _available else None


async def open_knowledge_base(run_id: str, snapshot: KnowledgeSnapshot) -> KnowledgeBase:
    """Store a run's knowledge where it is configured to live, and return a base to query it."""
    store = await get_graph_store()
    if store is None:
        return InMemoryKnowledgeBase(snapshot)
    try:
        await store.save(run_id, snapshot)
    except Exception:  # the boundary: the graph store must never fail a run
        log.exception("graph_store_write_failed", run_id=run_id)
        return InMemoryKnowledgeBase(snapshot)
    return store.base(run_id)


async def close_graph_store() -> None:
    """Close the current loop's driver. For shutdown, and for tests between loops."""
    store = _stores.pop(id(asyncio.get_running_loop()), None)
    if store is not None:
        await store.close()


def reset_graph_store_probe() -> None:
    """Forget the availability result. For tests, and after a configuration change."""
    global _available
    _available = None
