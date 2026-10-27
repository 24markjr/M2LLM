"""Whole-document reading (v4 Phase 2): when the documents fit, reasoning reads them in full.

The tools return what they extracted - a date, an amount, a matching passage - each beside its line
locator. That is how a large corpus fits a small model's prompt, and it is also why answers lost
what surrounded those values: B1 showed JARVIS naming IP addresses where the logs named hosts, and
stating a difference without the two figures it came from, while the plain model, reading the
whole files, stated both. So when every document together fits within half the observation
budget, reasoning also receives them whole, one numbered line each, every line citable. The tool
observations stay: they are what the plan asked for, and the trail shows them.

One observation, attributed to the task that read the documents, added after execution and before
the reasoning loop, so verification's evidence pool and the citation binder see every line too.
"""

from __future__ import annotations

from app.schemas.execution import Observation

WHOLE_DOCUMENT = "whole_document"


def whole_documents(
    documents: dict[str, str], *, task_id: str, budget_tokens: int
) -> Observation | None:
    """The documents in full as one observation, or None when they do not fit `budget_tokens`
    (four characters a token, the estimate compaction uses)."""
    lines: list[str] = []
    sources: list[str] = []
    for document in sorted(documents):
        lines.append(f"=== {document} ===")
        for number, text in enumerate(documents[document].splitlines(), start=1):
            if not text.strip():
                continue
            locator = f"{document}:r{number}"
            lines.append(f"[{locator}] {text.strip()}")
            sources.append(locator)
    content = "\n".join(lines)
    if not sources or len(content) // 4 > budget_tokens:
        return None
    return Observation(task_id=task_id, task_type=WHOLE_DOCUMENT, content=content, sources=sources)


def line_at(observation: Observation, locator: str) -> str:
    """The text of one line of a whole-document observation, by its locator."""
    prefix = f"[{locator}] "
    for line in observation.content.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return ""


def cite_by_values(claim: str, observation: Observation, limit: int = 6) -> list[str]:
    """Locators for a claim the model stated without citing (v4 Phase 2): for each date and figure
    in the claim, the first line that holds it. Every value must be found, or nothing is returned -
    a claim cited for half its values would look evidenced and is not. Verification then judges the
    claim against these lines exactly as against lines the model chose."""
    from app.intelligence.temporal import find_dates, find_figures

    dates = [d for _, d in find_dates(claim)]
    figures = {v for _, v in find_figures(claim)}
    if not dates and not figures:
        return []
    rows = [
        (line[1:].split("] ", 1)[0], line.split("] ", 1)[1])
        for line in observation.content.splitlines()
        if line.startswith("[") and "] " in line
    ]
    cited: list[str] = []
    for date in dates:
        hit = next(
            (loc for loc, text in rows if any(date.compatible(d) for _, d in find_dates(text))),
            None,
        )
        if hit is None:
            return []
        cited.append(hit)
    for figure in figures:
        hit = next(
            (loc for loc, text in rows if figure in {v for _, v in find_figures(text)}), None
        )
        if hit is None:
            return []
        cited.append(hit)
    return list(dict.fromkeys(cited))[:limit]
