"""Which chunks the knowledge pass reads, when it cannot read them all (BUG-034, 2026-10-07).

The knowledge pass makes one model call per chunk, bounded by `knowledge.max_chunks` (twelve by
default: about six minutes on `qwen3:4b`). Chunks used to be taken in order, so the first document
filled the budget: on twelve AURORA documents the pass read 12 of 191 chunks, nearly all from one
PDF, and the knowledge graph was effectively one document out of twelve.

Two rules now choose what is read, both deterministic - no model decides what the model reads:

1. **Every document gets a share.** The budget is dealt round-robin across documents, so each one is
   read before any is read twice.
2. **Within a document, the most relevant chunks first.** A chunk scores one point for each distinct
   word of the objective it contains, and half a point for holding a date and for holding a figure:
   the material a contradiction is made of. Ties keep document order.

What is read is then put back in document order, so names learned in one chunk carry into the next
(A8). What is not read is still counted (`chunks_skipped`), and `documents_read` says how many
documents contributed anything.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from app.intelligence.temporal import find_dates, find_figures

# Words that say nothing about what an objective is about.
_STOP = frozenset(
    """
    about above after again against also among and any are because been before being below between
    both but can could determine did does doing down during each establish evidence few find from
    further had has have having here how identify into investigate investigating its itself just
    more most must not now only other our out over own same should some such than that the their
    them then there these they this those through under until very was were what when where whether
    which while who whom why will with within would across available additional required before
    """.split()
)
_WORD = re.compile(r"[a-z][a-z0-9-]{3,}")


class _Chunk(Protocol):
    @property
    def document_id(self) -> str: ...

    @property
    def lines(self) -> tuple[tuple[int, str], ...]: ...


def objective_terms(objective: str) -> set[str]:
    """The words of an objective that say what it is about."""
    return {w for w in _WORD.findall(objective.lower()) if w not in _STOP}


def relevance(text: str, terms: set[str]) -> float:
    lowered = text.lower()
    score = float(sum(1 for term in terms if term in lowered))
    if find_dates(text):
        score += 0.5
    if find_figures(text):
        score += 0.5
    return score


def select_chunks[C: _Chunk](chunks: Sequence[C], budget: int, objective: str = "") -> list[C]:
    """At most `budget` chunks: a fair share per document, the most relevant of each first."""
    if len(chunks) <= budget:
        return list(chunks)
    terms = objective_terms(objective)
    order = {id(chunk): position for position, chunk in enumerate(chunks)}
    by_document: dict[str, list[C]] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.document_id, []).append(chunk)
    queues = [
        sorted(
            group,
            key=lambda c: (-relevance(" ".join(t for _, t in c.lines), terms), order[id(c)]),
        )
        for group in by_document.values()
    ]
    chosen: list[C] = []
    depth = 0
    while len(chosen) < budget and any(depth < len(q) for q in queues):
        for queue in queues:
            if depth < len(queue) and len(chosen) < budget:
                chosen.append(queue[depth])
        depth += 1
    return sorted(chosen, key=lambda c: order[id(c)])
