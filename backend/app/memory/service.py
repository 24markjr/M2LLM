"""Recording a finished run in memory, and finding the stores to read it back (Phase 33).

The same two rules as run persistence (`app/api/persistence.py`) and the graph store:

- **Memory is optional.** Episodic memory needs Postgres; semantic memory needs the configured
  graph store's home (Neo4j, or Postgres when the graph store is in memory). Whatever is missing,
  the run proceeds and the log says what was not recorded.
- **Memory never fails a run.** Every write is contained and logged.

And one rule of its own: **nothing here is called while a run is executing.** Memory is written
after the run has finished and is read only by the API, for people. A test asserts that the
orchestration and intelligence packages never import `app.memory`.
"""

from __future__ import annotations

from datetime import datetime

from app.api.persistence import persistence_enabled
from app.core.config import GraphStoreName, get_settings
from app.core.logging import get_logger
from app.database.session import session_scope
from app.integrations.graph_store import get_graph_store
from app.memory.distill import memory_record
from app.memory.episodic import EpisodicMemory
from app.memory.semantic import PostgresSemanticMemory, SemanticMemory
from app.orchestration.mission import MissionResult
from app.schemas.memory import MemoryRecord

log = get_logger(__name__)


async def get_semantic_memory() -> SemanticMemory | None:
    """Where facts live, by configuration; None when that store is unreachable."""
    if get_settings().graph_store is GraphStoreName.NEO4J:
        store = await get_graph_store()
        return store.semantic_memory() if store is not None else None
    return PostgresSemanticMemory() if await persistence_enabled() else None


async def episodic_available() -> bool:
    return await persistence_enabled()


async def record_run(result: MissionResult, *, started_at: datetime | None = None) -> MemoryRecord:
    """Record a finished run in memory. Never raises; returns what was derived."""
    record = memory_record(result, started_at)
    episodic = semantic = False

    if await episodic_available():
        try:
            async with session_scope() as session:
                await EpisodicMemory(session).record(record.investigation, record.episodes)
            episodic = True
        except Exception:  # the boundary: memory must never fail a run
            log.exception("memory_episodic_failed", run_id=result.run_id)

    memory = await get_semantic_memory()
    if memory is not None:
        try:
            await memory.record(record.entities, record.facts)
            semantic = True
        except Exception:  # the boundary: memory must never fail a run
            log.exception("memory_semantic_failed", run_id=result.run_id, store=memory.name)

    log.info(
        "memory_recorded",
        run_id=result.run_id,
        episodic=episodic,
        semantic=semantic,
        semantic_store=memory.name if memory is not None else "",
        episodes=len(record.episodes),
        entities=len(record.entities),
        facts=len(record.facts),
    )
    return record
