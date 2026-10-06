"""Test defaults, for the unit and integration suites.

**Tests never write to a real Neo4j by accident.** `GRAPH_STORE` defaults to `neo4j` (ADR-010), so
without this, a test that runs a comparative mission would store its knowledge graph in whatever
Neo4j a developer has running. That happened once, on 2026-10-03, and left five test runs in the
local database. Tests that exercise Neo4j (`test_knowledge_stores.py`) set the store themselves,
and clean up what they write.

**Unit tests never write to a real Postgres either** (Phase 33). Run persistence probes for a
database, and with Docker up a unit test's mission would be stored - and, since Phase 33, its
episodes and facts would appear in the developer's memory. Only tests marked `integration` see
the database; they create what they need and remove it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.api import persistence
from app.core.config import GraphStoreName, get_settings
from app.integrations import context as context_integration
from app.integrations import graph_store


@pytest.fixture(autouse=True)
def _knowledge_graphs_stay_in_memory(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.MEMORY)
    graph_store.reset_graph_store_probe()
    yield
    graph_store.reset_graph_store_probe()


@pytest.fixture(autouse=True)
def _no_media_understanding_by_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test reaches the vision model or Whisper by accident (Phase 39).

    Uploads and missions understand images, video and audio through the configured provider, which
    on a developer machine is a real Ollama. Off here; `test_media.py` turns it on with the echo
    provider and a temporary cache.
    """
    monkeypatch.setattr(get_settings(), "media_understanding", False)
    yield


@pytest.fixture(autouse=True)
def _unit_tests_have_no_database(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("integration") is None:
        persistence._available = False
        context_integration._database = False
    yield
    persistence.reset_persistence_probe()
    context_integration.reset_context_store_probe()
