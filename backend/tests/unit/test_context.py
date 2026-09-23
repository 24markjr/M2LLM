"""Phase 12 — context management and semantic retrieval.

The compaction tests carry the weight: compaction may lose prose, it may not lose
provenance. A summary without its source locators would make every claim built on it
unresolvable.
"""

from __future__ import annotations

import pytest

from app.integrations.context import ContextProvider, build_context_provider
from app.intelligence.context.manager import (
    ContextManager,
    LocalContextProvider,
    chunk_document,
    compact,
    cosine_similarity,
    estimate_tokens,
)
from app.llm.echo import EchoProvider
from app.schemas.execution import Observation

REPORT = """PROJECT HELIX - STATUS REPORT

The target completion date is 2026-04-30.
The approved budget is 380,000 for the migration phase.

Vendor availability remains the principal schedule risk.
"""


def _observation(task: str, sources: list[str], content: str = "x" * 400) -> Observation:
    return Observation(
        task_id=task,
        task_type="extract_timeline",
        content=content,
        structured={"extractions": [{"line": 1, "value": "2026-04-30"}]},
        sources=sources,
    )


# --- chunking: locators survive ------------------------------------------------


def test_chunks_carry_the_line_they_start_at() -> None:
    """Line-level locators are what let a retrieved passage become citable evidence."""
    chunks = chunk_document("report.txt", REPORT)
    assert chunks
    assert all(c.locator.row is not None for c in chunks)
    assert all(c.locator.document_id == "report.txt" for c in chunks)


def test_chunk_sources_render_as_citable_locators() -> None:
    chunk = chunk_document("report.txt", REPORT)[0]
    assert chunk.source.startswith("report.txt:r")


def test_an_empty_document_yields_no_chunks() -> None:
    assert chunk_document("empty.txt", "") == []


# --- similarity ----------------------------------------------------------------


def test_identical_vectors_score_one() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_opposite_vectors_score_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(0.0)


@pytest.mark.parametrize(("a", "b"), [([], [1.0]), ([1.0], []), ([1.0], [1.0, 2.0])])
def test_mismatched_vectors_score_zero_rather_than_raising(a: list[float], b: list[float]) -> None:
    assert cosine_similarity(a, b) == 0.0


# --- retrieval -----------------------------------------------------------------


async def test_ingest_indexes_every_chunk() -> None:
    provider = LocalContextProvider(EchoProvider(embedding_dim=32))
    count = await provider.ingest({"report.txt": REPORT})
    assert count > 0
    assert provider.chunk_count == count


async def test_retrieval_returns_scored_chunks_with_locators() -> None:
    provider = LocalContextProvider(EchoProvider(embedding_dim=32))
    await provider.ingest({"report.txt": REPORT})

    results = await provider.retrieve("completion date", k=3)

    assert results
    assert len(results) <= 3
    assert all(r.chunk.source.startswith("report.txt:r") for r in results)
    assert results == sorted(results, key=lambda r: r.score, reverse=True)


async def test_scope_restricts_retrieval_to_named_documents() -> None:
    provider = LocalContextProvider(EchoProvider(embedding_dim=32))
    await provider.ingest({"a.txt": REPORT, "b.txt": REPORT})

    results = await provider.retrieve("budget", k=10, scope=["a.txt"])

    assert results
    assert {r.chunk.locator.document_id for r in results} == {"a.txt"}


async def test_retrieval_before_ingest_returns_nothing() -> None:
    provider = LocalContextProvider(EchoProvider(embedding_dim=32))
    assert await provider.retrieve("anything") == []


async def test_an_empty_query_returns_nothing() -> None:
    provider = LocalContextProvider(EchoProvider(embedding_dim=32))
    await provider.ingest({"report.txt": REPORT})
    assert await provider.retrieve("   ") == []


# --- compaction: prose may go, provenance may not ------------------------------


def test_observations_within_budget_are_untouched() -> None:
    observations = [_observation("task_001", ["a.txt:r1"], content="short")]
    assert compact(observations, token_budget=6000) == observations


def test_compaction_preserves_every_source_locator() -> None:
    """The rule that makes compaction safe.

    A summary that loses its sources cannot support a finding - the binder would mark every
    claim built on it UNRESOLVED.
    """
    observations = [
        _observation("task_001", ["a.txt:r1", "a.txt:r2"]),
        _observation("task_002", ["b.txt:r7"]),
        _observation("task_003", ["c.txt:r3"]),
    ]
    before = {s for o in observations for s in o.sources}

    compacted = compact(observations, token_budget=10)

    after = {s for o in compacted for s in o.sources}
    assert after == before, "compaction must not lose a single locator"


def test_compaction_reduces_the_token_estimate() -> None:
    observations = [_observation(f"task_{i:03d}", [f"a.txt:r{i}"]) for i in range(1, 8)]
    compacted = compact(observations, token_budget=10)
    assert estimate_tokens(compacted) < estimate_tokens(observations)


def test_compacted_observations_are_marked_as_such() -> None:
    """Reasoning needs to know it is reading a summary rather than the original."""
    observations = [_observation(f"task_{i:03d}", [f"a.txt:r{i}"]) for i in range(1, 8)]
    compacted = compact(observations, token_budget=10)
    assert any(o.compacted for o in compacted)


def test_compaction_drops_structured_payloads_but_not_sources() -> None:
    observations = [_observation(f"task_{i:03d}", [f"a.txt:r{i}"]) for i in range(1, 8)]
    compacted = compact(observations, token_budget=10)
    first = compacted[0]
    assert first.structured == {}
    assert first.sources == ["a.txt:r1"]


# --- the manager ---------------------------------------------------------------


def test_the_manager_accumulates_observations_and_their_sources() -> None:
    manager = ContextManager()
    manager.record(_observation("task_001", ["a.txt:r1"]))
    manager.record(_observation("task_002", ["b.txt:r2"]))

    assert len(manager.observations) == 2
    assert manager.all_sources == {"a.txt:r1", "b.txt:r2"}


def test_the_verification_snapshot_contains_no_reasoning() -> None:
    """The absence is the contract (Phase 15).

    A verifier shown the argument tends to be persuaded by it.
    """
    manager = ContextManager()
    manager.record(_observation("task_001", ["a.txt:r1"]))

    snapshot = manager.snapshot_for_verification(
        "The dates conflict.", {"a.txt:r1": "target completion 2026-04-30"}
    )

    assert set(snapshot) == {"claim", "a.txt:r1"}
    assert "reasoning" not in snapshot
    assert "observations" not in snapshot


def test_the_reasoning_snapshot_compacts_when_over_budget() -> None:
    manager = ContextManager()
    for i in range(1, 8):
        manager.record(_observation(f"task_{i:03d}", [f"a.txt:r{i}"]))

    snapshot = manager.snapshot_for_reasoning(token_budget=10)
    assert {s for o in snapshot for s in o.sources} == manager.all_sources


# --- the provider seam ---------------------------------------------------------


def test_the_default_provider_satisfies_the_protocol() -> None:
    provider = build_context_provider(EchoProvider())
    assert isinstance(provider, ContextProvider)


def test_an_unconfigured_remote_provider_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run must not fail over a service that was never deployed."""
    from app.core.config import ProviderMode, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "context_provider", ProviderMode.REMOTE)
    monkeypatch.setattr(settings, "m2context_base_url", "")

    assert isinstance(build_context_provider(EchoProvider()), LocalContextProvider)
