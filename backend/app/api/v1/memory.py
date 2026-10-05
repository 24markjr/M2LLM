"""Memory routes (Phase 33): Member 4's episodic and semantic memory, for people to search.

| Member 4 | JARVIS |
|---|---|
| `EpisodicMemory.search(keyword, limit=5)` | `GET /api/v1/memory/episodes?q=&limit=` |
| `archive_investigation` (read back) | `GET /api/v1/memory/investigations/{run_id}` |
| `SemanticMemory.query(subject?, predicate?)` | `GET /api/v1/memory/facts?subject=&predicate=` |
| (new) | `GET /api/v1/memory/entities/{name}`: an entity across past investigations |
| (new) | `GET /api/v1/memory`: which tiers are available, and where facts are kept |

Read-only. Memory is written when a mission finishes (`app/memory/service.py`) and nothing here
feeds a running mission. A tier whose store is unreachable answers 503 `MEMORY_UNAVAILABLE`, so a
client can tell "no memory of this" from "memory is off".
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import Field

from app.api.errors import ApiError
from app.database.session import session_scope
from app.memory.episodic import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT, EpisodicMemory
from app.memory.semantic import SemanticMemory
from app.memory.service import episodic_available, get_semantic_memory
from app.schemas.common import JarvisModel
from app.schemas.memory import (
    DEFAULT_FACT_LIMIT,
    MAX_FACT_LIMIT,
    ArchivedInvestigation,
    EntityMemoryView,
    Episode,
    FactView,
)

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryStatus(JarvisModel):
    episodic: bool
    # Where facts are kept ("neo4j" or "postgres"), or empty when that store is unreachable.
    semantic_store: str = ""


class InvestigationMemory(JarvisModel):
    investigation: ArchivedInvestigation
    episodes: list[Episode] = Field(default_factory=list)


class MemoryUnavailableError(ApiError):
    def __init__(self, tier: str) -> None:
        super().__init__(
            "MEMORY_UNAVAILABLE",
            f"{tier} memory is not available: its store is not reachable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"tier": tier},
        )


class MemoryNotFoundError(ApiError):
    def __init__(self, what: str) -> None:
        super().__init__(
            "MEMORY_NOT_FOUND",
            f"no memory of {what}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


async def _episodic() -> None:
    if not await episodic_available():
        raise MemoryUnavailableError("episodic")


async def _semantic() -> SemanticMemory:
    memory = await get_semantic_memory()
    if memory is None:
        raise MemoryUnavailableError("semantic")
    return memory


@router.get("", response_model=MemoryStatus)
async def memory_status() -> MemoryStatus:
    memory = await get_semantic_memory()
    return MemoryStatus(
        episodic=await episodic_available(),
        semantic_store=memory.name if memory is not None else "",
    )


@router.get("/episodes", response_model=list[Episode])
async def episodes(
    q: str = "",
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
) -> list[Episode]:
    """Episodes whose objective or claim contains `q`, newest first."""
    await _episodic()
    async with session_scope() as session:
        return await EpisodicMemory(session).search(q, limit)


@router.get("/investigations/{run_id}", response_model=InvestigationMemory)
async def investigation(run_id: str) -> InvestigationMemory:
    await _episodic()
    async with session_scope() as session:
        memory = EpisodicMemory(session)
        archived = await memory.investigation(run_id)
        if archived is None:
            raise MemoryNotFoundError(f"investigation {run_id}")
        return InvestigationMemory(
            investigation=archived, episodes=await memory.episodes_of(run_id)
        )


@router.get("/facts", response_model=list[FactView])
async def facts(
    subject: str | None = None,
    predicate: str | None = None,
    limit: int = Query(default=DEFAULT_FACT_LIMIT, ge=1, le=MAX_FACT_LIMIT),
) -> list[FactView]:
    """Facts by exact subject and predicate (normalised), best supported first."""
    memory = await _semantic()
    found = await memory.facts(subject or None, predicate or None, limit)
    return [FactView.of(f) for f in found]


class Forgotten(JarvisModel):
    run_id: str
    episodes: int
    episodic: bool
    semantic: bool


@router.delete("/runs/{run_id}", response_model=Forgotten)
async def forget_run(run_id: str) -> Forgotten:
    """Remove what one mission contributed to memory: its episodes, its archived snapshot, its
    support for facts. A fact or entity nothing else supports goes with it; one other missions also
    saw stays, with their support. The mission itself and its recording are untouched."""
    episodes = 0
    episodic = await episodic_available()
    if episodic:
        async with session_scope() as session:
            episodes = await EpisodicMemory(session).forget(run_id)
    memory = await get_semantic_memory()
    if memory is not None:
        await memory.forget(run_id)
    if not episodic and memory is None:
        raise MemoryUnavailableError("episodic")
    return Forgotten(
        run_id=run_id, episodes=episodes, episodic=episodic, semantic=memory is not None
    )


@router.get("/entities/{name}", response_model=EntityMemoryView)
async def entity(name: str) -> EntityMemoryView:
    """An entity as seen across investigations, with the facts known about it."""
    memory = await _semantic()
    found = await memory.entity(name)
    if found is None:
        raise MemoryNotFoundError(f"entity {name!r}")
    return EntityMemoryView.of(found)
