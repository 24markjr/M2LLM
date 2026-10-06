"""Phase 40: stored, workspace-scoped retrieval (Member 2's ingest and search).

The echo provider's embeddings are hashes of the text: identical text gives an identical vector, so
a query that repeats a chunk's text finds that chunk. That checks the plumbing - scoping, citations,
idempotency, fallback - and says nothing about retrieval quality, which Experiment 006 measures.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.core.config import get_settings
from app.integrations import context as context_integration
from app.integrations.context import (
    StoreContextProvider,
    ingest_document,
    search_store,
    workspace_retriever,
)
from app.intelligence.context.store import MemoryContextStore, chunk_by_chars, chunk_text
from app.llm.echo import EchoProvider
from app.llm.provider import EmbeddingResponse
from app.schemas.tool import ToolCall
from app.tools.base import ToolContext, build_default_registry
from app.tools.builtin import ContextRetrievalTool

REPORT = """PROJECT HELIX - STATUS REPORT

The target completion date is 2026-04-30.
The approved budget is 380,000 for the migration phase.

Vendor availability remains the principal schedule risk.
"""
CHUNK_TWO = (
    "The target completion date is 2026-04-30.\n"
    "The approved budget is 380,000 for the migration phase."
)


@pytest.fixture(autouse=True)
def _fresh_memory_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[MemoryContextStore]:
    store = MemoryContextStore()
    monkeypatch.setattr(context_integration, "_memory_store", store)
    yield store


# --- chunking ------------------------------------------------------------------------------------


def test_the_char_chunker_overlaps_and_keeps_the_starting_line() -> None:
    text = "\n".join(f"line {n} " + "word " * 30 for n in range(1, 21))
    chunks = chunk_by_chars("long.txt", text, size=600, overlap=80)
    assert len(chunks) > 3
    assert chunks[0].locator.row == 1
    # Each later chunk starts inside the previous one (the overlap) and on the line its text is on.
    for chunk in chunks[1:]:
        start = int(chunk.chunk_id.rsplit(":c", 1)[1])
        assert chunk.locator.row == text.count("\n", 0, start) + 1
        assert not chunk.text.startswith(("ord", "rd"))  # never opens mid-word


def test_the_char_chunker_rejects_an_overlap_as_large_as_the_chunk() -> None:
    with pytest.raises(ValueError):
        chunk_by_chars("x.txt", "abc", size=80, overlap=80)


def test_the_configured_chunker_is_used() -> None:
    assert chunk_text("r.txt", REPORT, "lines")[0].chunk_id == "r.txt:1"
    assert chunk_text("r.txt", REPORT, "chars")[0].chunk_id == "r.txt:c0"


# --- ingest and search ---------------------------------------------------------------------------


async def test_ingest_is_idempotent_per_content(_fresh_memory_store: MemoryContextStore) -> None:
    llm = EchoProvider()
    first = await ingest_document(
        _fresh_memory_store, llm, workspace_id="w", document_id="r.txt", text=REPORT
    )
    again = await ingest_document(
        _fresh_memory_store, llm, workspace_id="w", document_id="r.txt", text=REPORT
    )
    changed = await ingest_document(
        _fresh_memory_store, llm, workspace_id="w", document_id="r.txt", text=REPORT + "More.\n"
    )
    assert first.chunks > 0 and not first.unchanged
    assert again.unchanged and again.chunks == first.chunks
    assert not changed.unchanged
    assert first.store == "memory"


async def test_search_is_scoped_by_workspace_and_document(
    _fresh_memory_store: MemoryContextStore,
) -> None:
    llm = EchoProvider()
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="a", document_id="r.txt", text=REPORT
    )
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="b", document_id="r.txt", text=REPORT
    )
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="a", document_id="o.txt", text=REPORT
    )

    hits = await search_store(_fresh_memory_store, llm, workspace_id="a", query=CHUNK_TWO, k=2)
    assert hits[0].score == pytest.approx(1.0)
    assert hits[0].chunk.source.split(":")[1] in {"r3", "r4"}

    only = await search_store(
        _fresh_memory_store, llm, workspace_id="a", query=CHUNK_TWO, k=10, document_ids=["o.txt"]
    )
    assert {h.chunk.locator.document_id for h in only} == {"o.txt"}
    assert await search_store(_fresh_memory_store, llm, workspace_id="c", query=CHUNK_TWO) == []
    assert await _fresh_memory_store.workspaces() == ["a", "b", "default"]


async def test_min_score_drops_weak_passages(_fresh_memory_store: MemoryContextStore) -> None:
    llm = EchoProvider()
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="w", document_id="r.txt", text=REPORT
    )
    hits = await search_store(
        _fresh_memory_store, llm, workspace_id="w", query=CHUNK_TWO, k=10, min_score=0.99
    )
    assert [h.chunk.source for h in hits] in (["r.txt:r3"], ["r.txt:r4"])


# --- the mission's tool --------------------------------------------------------------------------


async def test_the_tool_cites_stored_passages_when_given_a_retriever() -> None:
    retriever = await workspace_retriever("w", {"r.txt": REPORT}, [], EchoProvider())
    assert isinstance(retriever, StoreContextProvider)
    tool = ContextRetrievalTool(retriever)
    ctx = ToolContext(documents={"r.txt": REPORT}, document_ids=["r.txt"])
    result = await tool.execute(
        ToolCall(tool_name="context_retrieval", arguments={"query": CHUNK_TWO, "k": 1}), ctx
    )
    assert result.output["provider"] == "memory"
    assert result.sources in (["r.txt:r3"], ["r.txt:r4"])


async def test_the_tool_stays_inside_the_missions_documents() -> None:
    # The workspace holds another file; this mission did not attach it, so it is never cited.
    retriever = await workspace_retriever(
        "w", {"r.txt": REPORT, "other.txt": CHUNK_TWO}, [], EchoProvider()
    )
    tool = ContextRetrievalTool(retriever)
    ctx = ToolContext(documents={"r.txt": REPORT}, document_ids=["r.txt"])
    result = await tool.execute(
        ToolCall(tool_name="context_retrieval", arguments={"query": CHUNK_TWO, "k": 5}), ctx
    )
    assert all(s.startswith("r.txt:") for s in result.sources)


class _Broken:
    name = "broken"

    async def retrieve(self, query: str, *, k: int = 5, scope: list[str] | None = None) -> list:
        raise RuntimeError("store down")


async def test_a_failing_store_falls_back_to_lexical_search() -> None:
    tool = ContextRetrievalTool(_Broken())
    ctx = ToolContext(documents={"r.txt": REPORT}, document_ids=["r.txt"])
    result = await tool.execute(
        ToolCall(tool_name="context_retrieval", arguments={"query": "approved budget"}), ctx
    )
    assert not result.failed
    assert result.output["provider"] == "local"
    assert "lexical" in result.output["note"]
    assert "r.txt:r4" in result.sources


def test_without_a_retriever_the_registry_keeps_lexical_recall() -> None:
    plain = build_default_registry().get("context_retrieval")
    stored = build_default_registry(_Broken()).get("context_retrieval")
    assert isinstance(plain, ContextRetrievalTool) and plain._retriever is None
    assert isinstance(stored, ContextRetrievalTool) and stored._retriever is not None


# --- the API -------------------------------------------------------------------------------------


@pytest.fixture
def _uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    return tmp_path


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


@pytest.mark.usefixtures("_uploads")
async def test_an_upload_is_ingested_into_its_workspace_and_searchable() -> None:
    async with await _client() as client:
        uploaded = await client.post(
            "/api/v1/documents?workspace=helix",
            files=[("files", ("helix.txt", REPORT.encode()))],
        )
        assert uploaded.status_code == 201, uploaded.text
        ingested = uploaded.json()[0]["ingested"]
        assert ingested["workspace_id"] == "helix" and ingested["chunks"] > 0

        found = await client.post(
            "/api/v1/context/retrieve",
            json={"workspace_id": "helix", "query": CHUNK_TWO, "k": 1},
        )
        assert found.status_code == 200
        body = found.json()
        assert body["store"] == "memory"
        assert body["hits"][0]["source"] in {"helix.txt:r3", "helix.txt:r4"}

        assert "helix" in (await client.get("/api/v1/context/workspaces")).json()
        workspace = (await client.get("/api/v1/context/workspaces/helix")).json()
        assert [d["document_id"] for d in workspace["documents"]] == ["helix.txt"]
        assert len(workspace["documents"][0]["sha256"]) == 64


@pytest.mark.usefixtures("_uploads")
async def test_ingest_reports_what_it_could_not_read() -> None:
    async with await _client() as client:
        await client.post("/api/v1/documents", files=[("files", ("a.txt", REPORT.encode()))])
        response = await client.post(
            "/api/v1/context/ingest", json={"documents": ["a.txt", "nowhere.txt"]}
        )
    body = response.json()
    assert response.status_code == 200
    assert body["ingested"][0]["unchanged"] is True  # the upload already ingested it
    assert body["skipped"] == ["nowhere.txt"]


async def test_a_bad_workspace_name_is_rejected() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/context/retrieve", json={"workspace_id": "../etc", "query": "x"}
        )
    assert response.status_code == 422


@pytest.mark.usefixtures("_uploads")
async def test_a_mission_naming_a_workspace_searches_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import registry as registry_module

    registry_module.reset_registry()
    captured: dict[str, object] = {}

    async def create(**kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop here")  # the run itself is not under test

    monkeypatch.setattr(registry_module.get_registry(), "create", create)
    async with await _client() as client:
        await client.post("/api/v1/documents", files=[("files", ("m.txt", REPORT.encode()))])
        with pytest.raises(RuntimeError):
            await client.post(
                "/api/v1/missions",
                json={
                    "objective": "Check the Helix budget.",
                    "documents": ["m.txt"],
                    "workspace_id": "helix",
                },
            )
        assert isinstance(captured["retriever"], StoreContextProvider)
        workspace = (await client.get("/api/v1/context/workspaces/helix")).json()
    assert [d["document_id"] for d in workspace["documents"]] == ["m.txt"]
    registry_module.reset_registry()


class _Topical(EchoProvider):
    """Embeds by topic, so which line is closest to a query is known in advance."""

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[1.0, 0.0] if "budget" in t.lower() else [0.0, 1.0] for t in texts],
            model="topical",
        )


async def test_a_hit_is_cited_at_its_closest_line_not_its_heading(
    _fresh_memory_store: MemoryContextStore,
) -> None:
    # Measured on the Aurora reports: the first line of a matching chunk was its heading.
    text = "3. APPROVED BUDGET\nThe sponsor signed off on 12 May.\nThe budget is INR 380,000.\n"
    llm = _Topical()
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="w", document_id="a.txt", text=text
    )
    [hit] = await search_store(_fresh_memory_store, llm, workspace_id="w", query="budget", k=1)
    # Heading (r1) and amount (r3) both mention the budget; the first best line wins, never r2.
    assert hit.chunk.source == "a.txt:r1"
    plain = "Kickoff happened in March.\nThe budget is INR 380,000.\n"
    await ingest_document(
        _fresh_memory_store, llm, workspace_id="v", document_id="b.txt", text=plain
    )
    [hit] = await search_store(_fresh_memory_store, llm, workspace_id="v", query="budget", k=1)
    assert hit.chunk.source == "b.txt:r2"


def test_a_char_chunk_starting_at_a_newline_cites_the_line_its_text_is_on() -> None:
    text = "a" * 10 + "\n" + "second line here\nthird"
    chunks = chunk_by_chars("n.txt", text, size=12, overlap=1)
    for chunk in chunks:
        first = chunk.text.splitlines()[0]
        assert first in text.splitlines()[chunk.locator.row - 1]
