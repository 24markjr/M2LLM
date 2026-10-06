"""Experiment 006: retrieval, measured (Phase 41).

Phase 40 added search by meaning beside the lexical search and kept two chunkers, deciding nothing:
the defaults are this experiment's to set, as every default since Phase 34. Three arms search the
same corpus with the same queries (`.agent/evals/retrieval/queries.yaml`):

- `lexical`: the `document_search` tool, word overlap per line - what missions and evaluation use
- `semantic-lines`: embedded chunks of up to four lines (Phase 40's default)
- `semantic-chars`: Member 2's 600-character, 80-overlap chunks
- `hybrid-lines`: the lexical and `semantic-lines` rankings fused by reciprocal rank (added after
  the first run showed each search winning a different kind of query)

Scored per arm, from real searches (invariant 5; nothing here is estimated):

- **hit@1, hit@5**: answerable queries whose top 1 / top 5 cites a line a reader would cite
- **recall@5**: the share of all relevant lines cited in the top 5
- **MRR**: mean reciprocal rank of the first relevant citation
- **passage hit@5**: the relevant line is somewhere in a returned passage, cited or not - the gap
  between this and hit@5 is the cost of citing the wrong line of the right paragraph
- **separation** (semantic arms): the best score any unanswerable query got, and how many answerable
  queries' first relevant hit scored above it - what a `min_score` threshold could achieve

The semantic arms use the in-memory store: the store changes where vectors live, not what they
score, and the experiment must not depend on Docker. The embedding model is whatever the configured
provider serves; with the echo provider (tests, CI) the numbers mean nothing and the report says so.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import Field

from app.core.config import get_settings
from app.integrations.context import ingest_document, search_store
from app.intelligence.context.store import MemoryContextStore, fuse
from app.llm.provider import LLMProvider
from app.schemas.common import JarvisModel, utcnow
from app.schemas.tool import ToolCall
from app.tools.base import ToolContext
from app.tools.builtin import DocumentSearchTool
from app.tools.formats import prepare
from app.tools.loader import load_documents, resolve_document

ARMS = ("lexical", "semantic-lines", "semantic-chars", "hybrid-lines")
K = 5
WORKSPACE = "exp-006"


class RetrievalQuery(JarvisModel):
    id: str
    kind: str
    query: str
    relevant: list[str] = Field(default_factory=list)

    def relevant_lines(self) -> set[tuple[str, int]]:
        """`doc:rN` as (doc, N): compared by line, whatever form a citation is printed in."""
        out = set()
        for ref in self.relevant:
            document, _, row = ref.rpartition(":r")
            out.add((document, int(row)))
        return out


class Hit(JarvisModel):
    document_id: str
    line: int
    text: str
    score: float


class QueryResult(JarvisModel):
    id: str
    kind: str
    hits: list[Hit] = Field(default_factory=list)
    first_relevant_rank: int | None = None
    first_relevant_score: float | None = None
    relevant_cited: int = 0
    relevant_total: int = 0
    passage_hit: bool = False
    seconds: float = 0.0


class ArmReport(JarvisModel):
    arm: str
    chunks: int = 0
    ingest_s: float = 0.0
    mean_query_s: float = 0.0
    hit_at_1: float = 0.0
    hit_at_5: float = 0.0
    recall_at_5: float = 0.0
    mrr: float = 0.0
    passage_hit_at_5: float = 0.0
    # By kind: keyword and paraphrase, each with hit@1, hit@5 and MRR.
    by_kind: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Semantic arms only.
    best_unanswerable_score: float | None = None
    answerable_above_it: float | None = None
    queries: list[QueryResult] = Field(default_factory=list)


class RetrievalReport(JarvisModel):
    generated_at: str = Field(default_factory=lambda: utcnow().isoformat())
    embedding_model: str = ""
    provider: str = ""
    documents: int = 0
    queries: int = 0
    k: int = K
    arms: list[ArmReport] = Field(default_factory=list)
    # True when the embeddings are the echo provider's hashes: the plumbing ran, nothing measured.
    meaningless: bool = False


def queries_path() -> Path:
    return get_settings().agent_dir / "evals" / "retrieval" / "queries.yaml"


def experiment_dir() -> Path:
    return get_settings().agent_dir / "evals" / "experiments" / "exp-006-retrieval"


def load_benchmark(path: Path | None = None) -> tuple[list[str], list[RetrievalQuery]]:
    raw = yaml.safe_load((path or queries_path()).read_text(encoding="utf-8"))
    corpus = [str(name) for name in raw.get("corpus", [])]
    queries = [RetrievalQuery.model_validate(q) for q in raw.get("queries", [])]
    return corpus, queries


# --- scoring (pure) -------------------------------------------------------------------------------


def score_query(query: RetrievalQuery, hits: list[Hit], documents: dict[str, str]) -> QueryResult:
    """Where the first relevant citation is, how many relevant lines were cited, and whether a
    relevant line was inside a returned passage at all."""
    relevant = query.relevant_lines()
    result = QueryResult(id=query.id, kind=query.kind, hits=hits, relevant_total=len(relevant))
    cited = set()
    for rank, hit in enumerate(hits, start=1):
        key = (hit.document_id, hit.line)
        if key in relevant:
            cited.add(key)
            if result.first_relevant_rank is None:
                result.first_relevant_rank = rank
                result.first_relevant_score = hit.score
    result.relevant_cited = len(cited)
    wanted = [
        (d, documents[d].splitlines()[n - 1].strip())
        for d, n in relevant
        if d in documents and 0 < n <= len(documents[d].splitlines())
    ]
    result.passage_hit = bool(cited) or any(
        line and hit.document_id == d and line in hit.text for hit in hits for d, line in wanted
    )
    return result


def summarise(arm: str, results: list[QueryResult], *, semantic: bool) -> ArmReport:
    answerable = [r for r in results if r.relevant_total]
    report = ArmReport(arm=arm, queries=results)
    if answerable:
        report.hit_at_1 = _share(answerable, lambda r: r.first_relevant_rank == 1)
        report.hit_at_5 = _share(answerable, lambda r: r.first_relevant_rank is not None)
        report.recall_at_5 = sum(r.relevant_cited for r in answerable) / sum(
            r.relevant_total for r in answerable
        )
        report.mrr = statistics.fmean(
            1 / r.first_relevant_rank if r.first_relevant_rank else 0.0 for r in answerable
        )
        report.passage_hit_at_5 = _share(answerable, lambda r: r.passage_hit)
        for kind in sorted({r.kind for r in answerable}):
            group = [r for r in answerable if r.kind == kind]
            report.by_kind[kind] = {
                "hit_at_1": _share(group, lambda r: r.first_relevant_rank == 1),
                "hit_at_5": _share(group, lambda r: r.first_relevant_rank is not None),
                "mrr": statistics.fmean(
                    1 / r.first_relevant_rank if r.first_relevant_rank else 0.0 for r in group
                ),
            }
    if results:
        report.mean_query_s = statistics.fmean(r.seconds for r in results)
    unanswerable = [r for r in results if not r.relevant_total and r.hits]
    if semantic and unanswerable:
        ceiling = max(r.hits[0].score for r in unanswerable)
        report.best_unanswerable_score = round(ceiling, 4)
        report.answerable_above_it = (
            _share(
                answerable,
                lambda r: r.first_relevant_score is not None and r.first_relevant_score > ceiling,
            )
            if answerable
            else 0.0
        )
    return report


def _share(items: list[QueryResult], test: Callable[[QueryResult], bool]) -> float:
    return sum(1 for item in items if test(item)) / len(items)


# --- running --------------------------------------------------------------------------------------


async def run_retrieval_experiment(
    llm: LLMProvider, *, arms: tuple[str, ...] = ARMS, path: Path | None = None
) -> RetrievalReport:
    corpus, queries = load_benchmark(path)
    paths = [resolve_document(name) for name in corpus]
    await prepare(paths, llm)
    documents, _ = load_documents(paths)

    report = RetrievalReport(
        embedding_model=get_settings().embedding_model,
        provider=type(llm).__name__,
        documents=len(documents),
        queries=len(queries),
        meaningless=type(llm).__name__ == "EchoProvider",
    )
    for arm in arms:
        if arm == "lexical":
            report.arms.append(await _lexical(queries, documents))
        elif arm == "hybrid-lines":
            report.arms.append(await _hybrid(queries, documents, llm))
        else:
            report.arms.append(await _semantic(arm, queries, documents, llm))
    return report


async def _lexical_hits(query: str, documents: dict[str, str], k: int) -> list[Hit]:
    tool = DocumentSearchTool()
    ctx = ToolContext(documents=documents, document_ids=list(documents))
    output = await tool.execute(
        ToolCall(tool_name="document_search", arguments={"query": query, "k": k}), ctx
    )
    if output.failed:
        return []  # a query with no searchable words finds nothing, which is a result
    return [
        Hit(document_id=p["document_id"], line=p["line"], text=p["text"], score=p["score"])
        for p in (output.output or {}).get("passages", [])
    ]


async def _lexical(queries: list[RetrievalQuery], documents: dict[str, str]) -> ArmReport:
    results = []
    for query in queries:
        started = time.perf_counter()
        hits = await _lexical_hits(query.query, documents, K)
        result = score_query(query, hits, documents)
        result.seconds = time.perf_counter() - started
        results.append(result)
    return summarise("lexical", results, semantic=False)


async def _semantic(
    arm: str, queries: list[RetrievalQuery], documents: dict[str, str], llm: LLMProvider
) -> ArmReport:
    chunker = arm.removeprefix("semantic-")
    store = MemoryContextStore()
    started = time.perf_counter()
    chunks = 0
    for document_id, text in documents.items():
        done = await ingest_document(
            store, llm, workspace_id=WORKSPACE, document_id=document_id, text=text, chunker=chunker
        )
        chunks += done.chunks
    ingest_s = time.perf_counter() - started

    results = []
    for query in queries:
        started = time.perf_counter()
        found = await search_store(store, llm, workspace_id=WORKSPACE, query=query.query, k=K)
        hits = [
            Hit(
                document_id=h.chunk.locator.document_id,
                line=h.chunk.locator.row or 1,
                text=h.chunk.text,
                score=round(h.score, 4),
            )
            for h in found
        ]
        result = score_query(query, hits, documents)
        result.seconds = time.perf_counter() - started
        results.append(result)
    report = summarise(arm, results, semantic=True)
    report.chunks = chunks
    report.ingest_s = round(ingest_s, 2)
    return report


async def _hybrid(
    queries: list[RetrievalQuery], documents: dict[str, str], llm: LLMProvider
) -> ArmReport:
    store = MemoryContextStore()
    started = time.perf_counter()
    chunks = 0
    for document_id, text in documents.items():
        done = await ingest_document(
            store, llm, workspace_id=WORKSPACE, document_id=document_id, text=text, chunker="lines"
        )
        chunks += done.chunks
    ingest_s = time.perf_counter() - started

    results = []
    for query in queries:
        started = time.perf_counter()
        lexical = await _lexical_hits(query.query, documents, 2 * K)
        found = await search_store(store, llm, workspace_id=WORKSPACE, query=query.query, k=2 * K)
        semantic = [
            Hit(
                document_id=h.chunk.locator.document_id,
                line=h.chunk.locator.row or 1,
                text=h.chunk.text,
                score=h.score,
            )
            for h in found
        ]
        texts = {(h.document_id, h.line): h.text for h in [*lexical, *semantic]}
        fused = fuse(
            [
                [(h.document_id, h.line) for h in lexical],
                [(h.document_id, h.line) for h in semantic],
            ]
        )
        hits = [
            Hit(document_id=d, line=n, text=texts[(d, n)], score=round(score, 5))
            for (d, n), score in fused[:K]
        ]
        result = score_query(query, hits, documents)
        result.seconds = time.perf_counter() - started
        results.append(result)
    # Fused scores are ranks, not similarities: no separation is reported for this arm.
    report = summarise("hybrid-lines", results, semantic=False)
    report.chunks = chunks
    report.ingest_s = round(ingest_s, 2)
    return report


# --- reporting ------------------------------------------------------------------------------------


def to_markdown(report: RetrievalReport) -> str:
    lines = [
        "# Experiment 006: retrieval",
        "",
        f"**Generated:** {report.generated_at}  ",
        f"**Embeddings:** `{report.embedding_model}` via {report.provider}  ",
        f"**Corpus:** {report.documents} documents, {report.queries} queries, k = {report.k}",
        "",
        "All figures are computed from real searches over the committed fixtures.",
        "",
    ]
    if report.meaningless:
        lines += [
            "> **The echo provider's embeddings are hashes: these numbers measure the plumbing, "
            "not retrieval.**",
            "",
        ]
    lines += [
        "| Arm | hit@1 | hit@5 | recall@5 | MRR | passage hit@5 | chunks | ingest s | query s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in report.arms:
        lines.append(
            f"| {arm.arm} | {arm.hit_at_1:.3f} | {arm.hit_at_5:.3f} | {arm.recall_at_5:.3f} "
            f"| {arm.mrr:.3f} | {arm.passage_hit_at_5:.3f} | {arm.chunks or '-'} "
            f"| {arm.ingest_s or '-'} | {arm.mean_query_s:.3f} |"
        )
    lines += [
        "",
        "## By kind of query",
        "",
        "| Arm | Kind | hit@1 | hit@5 | MRR |",
        "|---|---|---|---|---|",
    ]
    for arm in report.arms:
        for kind, values in arm.by_kind.items():
            lines.append(
                f"| {arm.arm} | {kind} | {values['hit_at_1']:.3f} | {values['hit_at_5']:.3f} "
                f"| {values['mrr']:.3f} |"
            )
    semantic = [a for a in report.arms if a.best_unanswerable_score is not None]
    if semantic:
        lines += [
            "",
            "## Separation",
            "",
            "The best score any unanswerable query reached, and the share of answerable queries "
            "whose first relevant citation scored above it. A `min_score` threshold can only "
            "filter what sits below that line.",
            "",
            "| Arm | best unanswerable score | answerable above it |",
            "|---|---|---|",
        ]
        for arm in semantic:
            lines.append(
                f"| {arm.arm} | {arm.best_unanswerable_score:.3f} | {arm.answerable_above_it:.3f} |"
            )
    lines += ["", "## Per query (first relevant rank; - = not in the top 5)", ""]
    header = "| Query | Kind | " + " | ".join(a.arm for a in report.arms) + " |"
    lines += [header, "|" + "---|" * (2 + len(report.arms))]
    for index, query in enumerate(report.arms[0].queries if report.arms else []):
        ranks = []
        for arm in report.arms:
            result = arm.queries[index]
            if not result.relevant_total:
                top = f"{result.hits[0].score:.3f}" if result.hits else "none"
                ranks.append(f"top {top}")
            else:
                ranks.append(str(result.first_relevant_rank or "-"))
        lines.append(f"| {query.id} | {query.kind} | " + " | ".join(ranks) + " |")
    lines.append("")
    return "\n".join(lines)


def write_retrieval_report(report: RetrievalReport, directory: Path | None = None) -> Path:
    target = directory or experiment_dir()
    target.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at[:19].replace("-", "").replace(":", "")
    json_path = target / f"{stamp}-retrieval.json"
    md_path = target / f"{stamp}-retrieval.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return md_path
