"""Test defaults, for the unit and integration suites.

**Tests never write to a real Neo4j by accident.** `GRAPH_STORE` defaults to `neo4j` (ADR-010), so
without this, a test that runs a comparative mission would store its knowledge graph in whatever
Neo4j a developer has running. That happened once, on 2026-10-03, and left five test runs in the
local database. Tests that exercise Neo4j (`test_knowledge_stores.py`) set the store themselves,
and clean up what they write.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import GraphStoreName, get_settings
from app.integrations import graph_store


@pytest.fixture(autouse=True)
def _knowledge_graphs_stay_in_memory(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.MEMORY)
    graph_store.reset_graph_store_probe()
    yield
    graph_store.reset_graph_store_probe()
