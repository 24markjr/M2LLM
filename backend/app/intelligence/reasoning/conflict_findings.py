"""Contradictions the knowledge graph found, reported as findings (BUG-031, 2026-10-07).

The knowledge pass finds claims that disagree across documents, with both sides grounded on their
lines. Until now such a contradiction reached the report only if the reasoning model restated it as
a finding - and a 4B model often does not, even when the pair is handed to it (BUG-005/012). So a
contradiction can be in the graph, red, and absent from the report.

Here such a contradiction becomes a finding directly, built from its two cited lines without a
model. It is then verified like every other finding: nothing is reported because of where it came
from.

Only contradictions that can be one (BUG-033 split the rest off as differing descriptions), and of
those only the kind a reader can check at a glance:

- **dates or numbers** - text contradictions (short names, statuses) stay with reasoning, which can
  judge whether two names really name different things;
- **across two documents** - a pair within one document may be a planned and an actual date;
- **not document metadata** - a report's own date or version differs between reports by nature, the
  trap BUG-027 caught ("Date: 20 April 2026");
- **not already covered** - a finding that cites lines from two sides of it already reports it;
- **for a question that asks for a comparison** - the condition under which reasoning itself treats
  contradictions as the answer.
"""

from __future__ import annotations

import re

from app.intelligence.reasoning.engine import EvidenceBinder, source_agreement
from app.schemas.common import finding_id
from app.schemas.execution import Observation
from app.schemas.finding import Confidence, Finding, FindingClassification
from app.schemas.knowledge import ClaimConflict, ConflictKind, KnowledgeSnapshot

# Attributes that describe a document rather than the matter in it.
_METADATA = re.compile(
    r"^(document_?)?(date|dated|issue_?date|report_?date|version|revision|page|page_?count|id|"
    r"document_?id|reference|ref|prepared_?on|published|printed)$",
    re.IGNORECASE,
)


def _document(source: str) -> str:
    return source.rsplit(":", 1)[0] if ":" in source else source


def reportable(conflict: ClaimConflict) -> bool:
    if conflict.kind not in {ConflictKind.DATE, ConflictKind.NUMBER} or conflict.same_document:
        return False
    if _METADATA.match(conflict.attribute.strip().replace(" ", "_")):
        return False
    documents = {_document(s) for side in conflict.sides for s in side.sources}
    return len(documents) >= 2


def claim_of(conflict: ClaimConflict) -> str:
    """The contradiction in a sentence: what disagrees, and where each value is stated."""
    attribute = conflict.attribute.replace("_", " ")
    sides = "; ".join(f"{side.sources[0]} gives {side.value}" for side in conflict.sides)
    return f"The documents disagree on the {attribute} of {conflict.entity_name}: {sides}."


def covered(conflict: ClaimConflict, findings: list[Finding]) -> bool:
    """Whether some finding already cites lines from two different sides of the conflict."""
    side_sources = [set(side.sources) for side in conflict.sides]
    for finding in findings:
        cited = {ref.as_ref() for ref in finding.evidence if ref.is_resolved}
        if sum(1 for sources in side_sources if sources & cited) >= 2:
            return True
    return False


def conflict_findings(
    knowledge: KnowledgeSnapshot | None,
    findings: list[Finding],
    observations: list[Observation],
    *,
    comparative: bool,
) -> list[Finding]:
    """New findings for the reportable contradictions no existing finding reports."""
    if knowledge is None or not comparative:
        return []
    binder = EvidenceBinder(observations)
    taken = {f.finding_id for f in findings}
    next_number = len(findings) + 1
    added: list[Finding] = []
    for conflict in knowledge.conflicts:
        if not reportable(conflict) or covered(conflict, [*findings, *added]):
            continue
        citations = [side.sources[0] for side in conflict.sides]
        refs, _ = binder.bind(citations)
        if sum(1 for ref in refs if ref.is_resolved) < 2:
            continue  # both sides must resolve against what the run actually retrieved
        while finding_id(next_number) in taken:
            next_number += 1
        finding = Finding(
            finding_id=finding_id(next_number),
            claim=claim_of(conflict),
            classification=FindingClassification.UNKNOWN,
            evidence=refs,
            # What the knowledge graph found it to be; typed by the same rule as any finding.
            proposed_type="CONTRADICTION",
            derived_from_task_ids=sorted(
                {o.task_id for o in observations if set(o.sources) & set(citations)}
            ),
        )
        finding.classification = finding.classify()
        finding.confidence = Confidence.compute(
            refs=refs,
            source_agreement=source_agreement(refs),
            classification=finding.classification,
        )
        taken.add(finding.finding_id)
        added.append(finding)
    return added
