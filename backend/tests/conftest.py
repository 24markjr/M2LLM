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
from pathlib import Path

import pytest

from app.api import persistence
from app.auth import service as auth_service
from app.cases import service as case_service
from app.cases.store import MemoryCaseStore
from app.core.config import GraphStoreName, get_settings
from app.evidence import service as evidence_service
from app.evidence import store as evidence_store
from app.evidence.locker import MemoryEvidenceLocker
from app.integrations import context as context_integration
from app.integrations import graph_store
from app.review import service as review_service
from app.review.store import MemoryReviewStore


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
def _evidence_stays_in_the_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test writes to the real Evidence Locker (Phase 43).

    Custody is append-only - in Postgres a trigger refuses to delete it - so a test that recorded
    custody in a developer's database could never be cleaned up. Every test gets a fresh in-memory
    locker and a temporary evidence folder; the Postgres locker's own tests construct it with a
    transaction they roll back (tests/integration/test_evidence_locker.py).
    """
    monkeypatch.setattr(evidence_store, "evidence_root", lambda: tmp_path / "evidence-store")
    monkeypatch.setattr(evidence_service, "_memory_locker", MemoryEvidenceLocker())
    monkeypatch.setattr(evidence_service, "_database", False)
    monkeypatch.setattr(evidence_service, "_checked_at", None)  # never re-probed (U1)
    # Cases too (Phase 44): a fresh memory store per test, never a developer's database.
    monkeypatch.setattr(case_service, "_memory_store", MemoryCaseStore())
    monkeypatch.setattr(case_service, "_database", False)
    monkeypatch.setattr(case_service, "_checked_at", None)  # never re-probed (U1)
    # Reviews and the audit log too (Phase 50): append-only in Postgres, so never a real database.
    monkeypatch.setattr(review_service, "_memory_store", MemoryReviewStore())
    monkeypatch.setattr(review_service, "_database", False)
    monkeypatch.setattr(review_service, "_checked_at", None)  # never re-probed (U1)
    yield


@pytest.fixture(autouse=True)
def _runs_are_recorded_in_the_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """No test writes a recording or a run archive into the real `.agent/` (BUG-040).

    `test_api_persistence.py` started real missions, and each one left a recording in
    `.agent/traces/`: 80 of the 101 recordings on the console's Replay page were these, failed runs
    named "Investigate the reports for contradictions.". Since Phase U1 archives would also be
    restored as investigations, so a leak would now show up in everyone's history.
    """
    monkeypatch.setattr("app.api.recording.recordings_dir", lambda: tmp_path / "traces")
    monkeypatch.setattr("app.api.archive.archives_dir", lambda: tmp_path / "runs")
    yield


@pytest.fixture(autouse=True)
def _unit_tests_have_no_database(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("integration") is None:
        persistence._available = False
        context_integration._database = False
        # v4 Phase 1a: the account store and the audit log probe the database too.
        auth_service._database, auth_service._checked_at = False, None
        review_service._database, review_service._checked_at = False, None
    yield
    persistence.reset_persistence_probe()
    context_integration.reset_context_store_probe()
    auth_service._database = auth_service._checked_at = None
    review_service._database = review_service._checked_at = None


def _media_installed() -> bool:
    from importlib.util import find_spec

    return all(find_spec(m) is not None for m in ("rapidocr_onnxruntime", "pypdfium2", "av"))


# Tests that run OCR, render a scanned page or decode audio need the optional `media` extra.
# Found by the Phase 42 clean-clone check: with the base install the README describes, eight tests
# failed on a missing module instead of saying what to install. CI installs the extra, so they still
# run there.
requires_media = pytest.mark.skipif(
    not _media_installed(),
    reason='needs the media extra: pip install -e "backend[media]"',
)


@pytest.fixture(autouse=True)
def _accounts_off_unless_tested(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """v4 Phase 1a: the suite predates accounts and tests the routes, not the sign-in in front of
    them. tests/unit/test_auth.py switches accounts back on for itself."""
    monkeypatch.setattr(get_settings(), "auth_required", False)
    yield
