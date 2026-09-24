"""The reasoning engine — observations into structured, evidence-bound findings.

This is where the project's central claim is either earned or lost.

The model reads the observations and proposes claims with citations. It would be easy to
take those at face value: the output looks authoritative, the citations look like locators,
and nothing would obviously break. **The binder is what stops that.** Every citation is
resolved against locators that tasks actually produced. A citation that cannot be matched is
kept and marked `UNRESOLVED` rather than dropped, because a dropped citation makes a claim
look better supported than it is.

Classification and confidence are then *computed* from what resolved. The model's suggested
classification is advisory, and it is never asked for a confidence number at all - there is
nowhere in the type system to put one.
"""

from __future__ import annotations

import re

from pydantic import Field

from app.core.agent_config import get_models_config
from app.core.logging import get_logger
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel, SourceLocator, evidence_id, finding_id
from app.schemas.event import EventType
from app.schemas.evidence import (
    Evidence,
    EvidenceRef,
    EvidenceStrength,
    ResolutionStatus,
)
from app.schemas.execution import Observation
from app.schemas.finding import Confidence, Finding, FindingClassification
from app.schemas.objective import Objective

log = get_logger(__name__)


class CandidateFinding(JarvisModel):
    """A claim as the model proposes it, before anything has been checked.

    `confidence` is accepted and then thrown away. The prompt tells the model not to report
    one, and it does anyway - which under `extra="forbid"` burned the entire repair budget on
    a field we were always going to ignore. Declaring it is the honest fix: the value is
    parsed, discarded, and confidence is computed from resolved evidence as it always was.
    Silently trusting it would be the failure; refusing to parse it is merely wasteful.
    """

    claim: str = ""
    citations: list[str] = Field(default_factory=list)
    classification: str = "UNKNOWN"
    reasoning_step: str = ""
    confidence: float | None = Field(default=None, exclude=True)
    evidence: list[str] = Field(default_factory=list)

    @property
    def all_citations(self) -> list[str]:
        """Models put locators under either name. Both are read; neither is trusted."""
        return [*self.citations, *self.evidence]


class CandidateFindings(JarvisModel):
    findings: list[CandidateFinding] = Field(default_factory=list)


# A locator, optionally followed by whatever else the model appended. Models routinely
# quote the cited line after the reference - "report.txt:r7: Project Aurora is a..." - and
# splitting on the last colon would read the prose as the position and reject the whole
# citation. Anchoring at the start and ignoring the remainder accepts the reference the
# model actually meant, without accepting a reference it did not make.
_LOCATOR = re.compile(r"^\s*(?P<document>[^\s:]+?)\s*:\s*(?P<kind>[rpc]?)(?P<number>\d+)\b")


def parse_locator(raw: str) -> SourceLocator | None:
    """Turn `project_report.txt:r10` into a structured locator.

    Returns None for anything with no locator in it at all, which is itself a signal: a
    model inventing a citation usually invents the format too.
    """
    match = _LOCATOR.match(raw.strip())
    if match is None:
        return None

    document = match.group("document")
    value = int(match.group("number"))
    if match.group("kind") == "p":
        return SourceLocator(document_id=document, document_name=document, page=value)
    return SourceLocator(document_id=document, document_name=document, row=value)


class EvidenceBinder:
    """Resolves cited locators against what the tasks actually produced.

    The single most important component in the system. Without it, "evidence-backed" means
    only that the model wrote something in an evidence-shaped field.
    """

    def __init__(self, observations: list[Observation]) -> None:
        self._available: set[str] = {s for o in observations for s in o.sources}
        self._by_source: dict[str, Observation] = {s: o for o in observations for s in o.sources}
        self._counter = 0

    @property
    def available_locators(self) -> set[str]:
        return set(self._available)

    def bind(self, citations: list[str]) -> tuple[list[EvidenceRef], list[Evidence]]:
        """Resolve each citation. Unresolvable ones are kept and marked, never dropped."""
        refs: list[EvidenceRef] = []
        evidence: list[Evidence] = []

        for raw in citations:
            locator = parse_locator(raw)
            if locator is None:
                refs.append(
                    EvidenceRef(
                        locator=SourceLocator(document_id=raw.strip() or "unknown"),
                        resolution=ResolutionStatus.UNRESOLVED,
                        resolution_note="citation is not a well-formed locator",
                    )
                )
                continue

            key = locator.as_ref()
            if key not in self._available:
                refs.append(
                    EvidenceRef(
                        locator=locator,
                        resolution=ResolutionStatus.UNRESOLVED,
                        resolution_note="no task produced this locator",
                    )
                )
                continue

            self._counter += 1
            item = Evidence(
                evidence_id=evidence_id(self._counter),
                locator=locator,
                content=self._content_for(key),
                strength=EvidenceStrength.DIRECT,
                retrieved_by_task_id=self._by_source[key].task_id,
            )
            evidence.append(item)
            refs.append(item.to_ref())

        return refs, evidence

    def _content_for(self, key: str) -> str:
        observation = self._by_source.get(key)
        if observation is None:
            return key
        return f"{key}: {observation.content}"


def source_agreement(refs: list[EvidenceRef]) -> float:
    """How much independent support a claim has.

    One source is taken at its word. Two or more distinct documents agreeing is worth more,
    which is what separates an INFERENCE from a single-source assertion.
    """
    resolved = [r for r in refs if r.is_resolved]
    if not resolved:
        return 0.0
    documents = {r.locator.document_id for r in resolved}
    return 1.0 if len(documents) >= 2 else 0.85


class ReasoningEngine:
    """Derives findings from observations, binding every claim to real evidence."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def derive_findings(
        self,
        objective: Objective,
        observations: list[Observation],
        *,
        emit: object | None = None,
        start_index: int = 0,
    ) -> list[Finding]:
        if not observations:
            return []

        # Bound the prompt. Compaction preserves every source locator, so a compacted
        # observation still supports a citable claim - the binder resolves against
        # `sources`, which compaction never touches. Without this the prompt grows with the
        # corpus and a local model stalls before producing anything.
        from app.intelligence.context.manager import compact

        budget = get_models_config().params_for("reasoning").max_tokens
        bounded = compact(observations, token_budget=budget)

        await self._event(emit, EventType.REASONING_STARTED, {"observations": len(bounded)})

        candidates = await self._ask_model(objective, bounded, emit)
        binder = EvidenceBinder(observations)
        findings: list[Finding] = []

        for offset, candidate in enumerate(candidates.findings, start=start_index + 1):
            claim = candidate.claim.strip()
            if not claim:
                continue

            refs, _evidence = binder.bind(candidate.all_citations)
            finding = Finding(
                finding_id=finding_id(offset),
                claim=claim,
                classification=FindingClassification.UNKNOWN,
                evidence=refs,
                derived_from_task_ids=sorted({o.task_id for o in observations}),
            )

            # Classification is recomputed from what resolved. The model's suggestion is
            # advisory and the stricter answer wins.
            finding.classification = finding.classify()
            finding.confidence = Confidence.compute(
                refs=refs,
                source_agreement=source_agreement(refs),
                classification=finding.classification,
            )

            findings.append(finding)
            await self._event(
                emit,
                EventType.FINDING_CREATED,
                {
                    "claim": claim[:160],
                    "classification": finding.classification.value,
                    "confidence": round(finding.confidence.value, 3),
                    "resolved_evidence": finding.resolved_evidence_count,
                    "cited": len(refs),
                },
                finding_id=finding.finding_id,
            )

        unresolved = sum(len(f.evidence) - f.resolved_evidence_count for f in findings)
        if unresolved:
            log.warning("unresolved_citations", count=unresolved)

        return findings

    async def _ask_model(
        self, objective: Objective, observations: list[Observation], emit: object | None
    ) -> CandidateFindings:
        prompt = self._prompts.get("reasoning").render(
            objective=objective.text,
            observations=self._describe(observations),
        )
        try:
            return await generate_structured(
                self._provider, CandidateFindings, prompt, role="reasoning", emit=emit
            )
        except StructuredOutputError:
            # No findings is an honest outcome. Inventing one to fill the gap is not.
            log.warning("reasoning_structured_output_failed")
            return CandidateFindings()

    @staticmethod
    def _describe(observations: list[Observation]) -> str:
        """Render observations with their locators, so citations can be copied verbatim."""
        lines: list[str] = []
        for observation in observations:
            lines.append(
                f"\n[{observation.task_id}] {observation.task_type}: {observation.content}"
            )
            for source in observation.sources:
                detail = _detail_for(observation, source)
                lines.append(f"  - {source}{detail}")
        return "\n".join(lines)

    @staticmethod
    async def _event(
        emit: object | None,
        event_type: EventType,
        payload: dict[str, object],
        *,
        finding_id: str | None = None,
    ) -> None:
        if emit is None:
            return
        emitter = getattr(emit, "emit", None)
        if emitter is None:
            return
        await emitter(event_type, payload=payload, finding_id=finding_id)


def _detail_for(observation: Observation, source: str) -> str:
    """Attach the extracted value to a locator where the tool recorded one.

    Without this the model sees a list of line references with no content and has to guess
    what they contain - which is exactly how unresolvable citations get produced.
    """
    structured = observation.structured
    row = source.rpartition(":r")[2]
    if not row.isdigit():
        return ""
    line = int(row)

    for key in ("extractions", "passages"):
        items = structured.get(key)
        if not isinstance(items, list):
            continue
        values = [
            str(item.get("value") or item.get("text", ""))
            for item in items
            if isinstance(item, dict) and item.get("line") == line
        ]
        if values:
            return "  " + " | ".join(v[:120] for v in values[:3])
    return ""
