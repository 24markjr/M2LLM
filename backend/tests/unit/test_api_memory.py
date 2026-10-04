"""Phase 33: memory with no store reachable, and memory that fails.

The unit suite has no database (tests/conftest.py) and keeps graphs in memory, which is exactly
the laptop-without-Docker case: memory must be off, say so, and never get in a run's way.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import registry
from app.api.app import create_app
from app.memory import service
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import new_run_id
from app.schemas.knowledge import EntityType, KnowledgeEntity, KnowledgeSnapshot
from app.schemas.memory import EntityMemory, Fact, KnownEntity
from app.schemas.objective import Objective


def _result() -> MissionResult:
    return MissionResult(
        run_id=new_run_id(),
        objective=Objective(text="Who received shipment 4821?"),
        status=MissionStatus.COMPLETED,
        knowledge=KnowledgeSnapshot(
            entities=[
                KnowledgeEntity(
                    entity_id="ENT-001", name="Rahul Sharma", entity_type=EntityType.PERSON
                )
            ]
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_memory_reports_itself_off() -> None:
    async with await _client() as client:
        assert (await client.get("/api/v1/memory")).json() == {
            "episodic": False,
            "semantic_store": "",
        }


@pytest.mark.parametrize(
    ("path", "tier"),
    [
        ("/api/v1/memory/episodes?q=shipment", "episodic"),
        ("/api/v1/memory/investigations/run_00000000a001", "episodic"),
        ("/api/v1/memory/facts?subject=Rahul", "semantic"),
        ("/api/v1/memory/entities/Rahul Sharma", "semantic"),
    ],
)
async def test_a_tier_without_its_store_answers_503(path: str, tier: str) -> None:
    async with await _client() as client:
        response = await client.get(path)
    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "MEMORY_UNAVAILABLE"
    assert body["details"] == {"tier": tier}


async def test_the_episode_limit_is_bounded() -> None:
    async with await _client() as client:
        assert (await client.get("/api/v1/memory/episodes?limit=500")).status_code == 422


async def test_recording_with_no_store_is_a_silent_no_op() -> None:
    record = await service.record_run(_result())
    # Derived all the same, so the log can say what was not stored.
    assert [e.key for e in record.entities] == ["rahul sharma"]


class _BrokenMemory:
    name = "broken"

    async def record(self, entities: list[KnownEntity], facts: list[Fact]) -> None:
        raise ConnectionError("store went away")

    async def entity(self, name: str) -> EntityMemory | None:
        raise ConnectionError("store went away")

    async def facts(
        self, subject: str | None = None, predicate: str | None = None, limit: int = 50
    ) -> list[Fact]:
        raise ConnectionError("store went away")

    async def forget(self, run_id: str) -> None:
        raise ConnectionError("store went away")


async def test_a_failing_store_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken() -> _BrokenMemory:
        return _BrokenMemory()

    monkeypatch.setattr(service, "get_semantic_memory", broken)
    record = await service.record_run(_result())
    assert len(record.entities) == 1


async def test_memory_failing_outright_never_fails_the_mission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("a bug in distillation")

    monkeypatch.setattr(registry, "record_run", explode)
    await registry._record_memory(_result(), None)  # contained: does not raise
