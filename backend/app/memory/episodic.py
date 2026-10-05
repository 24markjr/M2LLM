"""Episodic memory in Postgres (T11): archived investigations, and one episode per finding.

Member 4 kept these in a SQLite file next to the module and searched with `LIKE` on the question
or the answer, newest first, five by default. The search is the same, as `ILIKE` on the objective
or the claim. Recording a run twice replaces what it recorded the first time, so a run's memory is
always exactly what its last recording derived.
"""

from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import MemoryEpisode, MemoryInvestigation
from app.schemas.memory import ArchivedInvestigation, Episode, WorkingMemorySnapshot

# Member 4's default for `search(keyword, limit=5)`.
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 50


class EpisodicMemory:
    """Episodes and archived investigations. Like the repositories, it is handed a session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, investigation: ArchivedInvestigation, episodes: list[Episode]) -> None:
        """Archive a run and log its episodes, replacing any earlier recording of the run."""
        snapshot = investigation.snapshot.model_dump(mode="json")
        statement = insert(MemoryInvestigation).values(
            run_id=investigation.run_id,
            objective=investigation.objective,
            snapshot=snapshot,
            archived_at=investigation.archived_at,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[MemoryInvestigation.run_id],
                set_={
                    "objective": statement.excluded.objective,
                    "snapshot": statement.excluded.snapshot,
                    "archived_at": statement.excluded.archived_at,
                },
            )
        )
        await self._session.execute(
            delete(MemoryEpisode).where(MemoryEpisode.run_id == investigation.run_id)
        )
        self._session.add_all(
            MemoryEpisode(
                episode_id=e.episode_id,
                run_id=e.run_id,
                objective=e.objective,
                claim=e.claim,
                sources=list(e.sources),
                verification_status=e.verification_status,
                created_at=e.created_at,
            )
            for e in episodes
        )
        await self._session.flush()

    async def forget(self, run_id: str) -> int:
        """Remove a run's episodes and its archived snapshot. Returns how many episodes went."""
        removed = await self._session.execute(
            delete(MemoryEpisode).where(MemoryEpisode.run_id == run_id)
        )
        await self._session.execute(
            delete(MemoryInvestigation).where(MemoryInvestigation.run_id == run_id)
        )
        return int(getattr(removed, "rowcount", 0) or 0)

    async def search(self, keyword: str = "", limit: int = DEFAULT_SEARCH_LIMIT) -> list[Episode]:
        """Episodes whose objective or claim contains `keyword`, newest first. Empty: all."""
        query = select(MemoryEpisode)
        keyword = keyword.strip()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            query = query.where(
                or_(
                    MemoryEpisode.objective.ilike(pattern, escape="\\"),
                    MemoryEpisode.claim.ilike(pattern, escape="\\"),
                )
            )
        query = query.order_by(MemoryEpisode.created_at.desc(), MemoryEpisode.episode_id).limit(
            max(1, min(limit, MAX_SEARCH_LIMIT))
        )
        rows = (await self._session.execute(query)).scalars()
        return [_episode(row) for row in rows]

    async def episodes_of(self, run_id: str) -> list[Episode]:
        rows = await self._session.execute(
            select(MemoryEpisode)
            .where(MemoryEpisode.run_id == run_id)
            .order_by(MemoryEpisode.episode_id)
        )
        return [_episode(row) for row in rows.scalars()]

    async def investigation(self, run_id: str) -> ArchivedInvestigation | None:
        row = await self._session.get(MemoryInvestigation, run_id)
        if row is None:
            return None
        return ArchivedInvestigation(
            run_id=row.run_id,
            objective=row.objective,
            snapshot=WorkingMemorySnapshot.model_validate(row.snapshot),
            archived_at=row.archived_at,
        )


def _episode(row: MemoryEpisode) -> Episode:
    return Episode(
        episode_id=row.episode_id,
        run_id=row.run_id,
        objective=row.objective,
        claim=row.claim,
        sources=list(row.sources),
        verification_status=row.verification_status,
        created_at=row.created_at,
    )


def _escape_like(text: str) -> str:
    """A search for `100%` means the text `100%`, not a wildcard."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
