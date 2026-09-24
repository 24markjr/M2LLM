"""The intent engine — ambiguous natural language to a validated `Intent`.

The first real agent behaviour in the system. Three design decisions shape it:

**The model proposes operations as free text; the system maps them to a closed vocabulary.**
A model that invents `analyze_everything` does not get it silently accepted. Unknown
operations become `UnsupportedOperation` entries that surface in the report's Limitations
section, because an agent that quietly ignores part of a request and reports success has
lied about what it did.

**A deterministic pre-pass runs before the model.** File types and comparison keywords are
structural facts about the request. Deriving them in code means the model is never the only
signal, and the engine degrades to something useful rather than nothing if the model fails.

**Ambiguity is a valid answer.** "Look at these files" must produce
`clarification_needed=True`, not a confident plan. Guessing is the failure mode here, not
the recovery.
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
from app.schemas.common import JarvisModel
from app.schemas.event import EventType
from app.schemas.intent import (
    SUPPORTING_OPERATIONS,
    Constraints,
    Intent,
    Operation,
    OutputFormat,
    RequiredOperation,
    UnsupportedOperation,
)
from app.schemas.objective import DocumentKind, Objective

log = get_logger(__name__)


class CandidateIntent(JarvisModel):
    """What the model returns, before validation.

    Operations are plain strings here on purpose. Constraining the model to an enum tends to
    produce a silent nearest-match; letting it answer freely and mapping afterwards means an
    out-of-vocabulary request is *visible* rather than quietly rounded off.
    """

    goal: str = ""
    objective: str = ""
    operations: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    evidence_required: bool = True
    output_format: str = "investigation_report"
    clarification_needed: bool = False
    clarification_question: str = ""


# Phrasings that map onto the closed vocabulary. Small and explicit: a fuzzy matcher here
# would reintroduce exactly the silent nearest-match problem this design avoids.
_SYNONYMS: dict[str, Operation] = {
    "read_documents": Operation.PROCESS_DOCUMENTS,
    "parse_documents": Operation.PROCESS_DOCUMENTS,
    "ingest_documents": Operation.PROCESS_DOCUMENTS,
    "extract_dates": Operation.EXTRACT_TIMELINE,
    "extract_schedule": Operation.EXTRACT_TIMELINE,
    "extract_timeline_information": Operation.EXTRACT_TIMELINE,
    "extract_costs": Operation.EXTRACT_BUDGET,
    "extract_financials": Operation.EXTRACT_BUDGET,
    "extract_budget_information": Operation.EXTRACT_BUDGET,
    "compare": Operation.COMPARE_SOURCES,
    "cross_reference": Operation.COMPARE_SOURCES,
    "compare_documents": Operation.COMPARE_SOURCES,
    "find_inconsistencies": Operation.DETECT_INCONSISTENCIES,
    "identify_inconsistencies": Operation.DETECT_INCONSISTENCIES,
    "find_contradictions": Operation.DETECT_CONTRADICTIONS,
    "identify_contradictions": Operation.DETECT_CONTRADICTIONS,
    "calculate": Operation.CALCULATE_DIFFERENCE,
    "compute_difference": Operation.CALCULATE_DIFFERENCE,
    "find_evidence": Operation.RETRIEVE_EVIDENCE,
    "gather_evidence": Operation.RETRIEVE_EVIDENCE,
    "verify": Operation.VERIFY_FINDINGS,
    "validate_findings": Operation.VERIFY_FINDINGS,
    "assess_impact_of_delay": Operation.ASSESS_IMPACT,
    "write_report": Operation.GENERATE_REPORT,
    "produce_report": Operation.GENERATE_REPORT,
}

# Keyword signals for the deterministic pre-pass.
_KEYWORDS: list[tuple[re.Pattern[str], Operation]] = [
    (
        re.compile(r"\b(timeline|schedule|deadline|milestone date)", re.I),
        Operation.EXTRACT_TIMELINE,
    ),
    (re.compile(r"\b(budget|cost|spend|financial|expenditure)", re.I), Operation.EXTRACT_BUDGET),
    (re.compile(r"\b(milestone)", re.I), Operation.EXTRACT_MILESTONES),
    (re.compile(r"\b(compare|versus|against|cross.?reference)", re.I), Operation.COMPARE_SOURCES),
    (
        re.compile(r"\b(inconsisten|mismatch|discrepan|do not match)", re.I),
        Operation.DETECT_INCONSISTENCIES,
    ),
    (re.compile(r"\b(contradict|conflict|disagree)", re.I), Operation.DETECT_CONTRADICTIONS),
    (re.compile(r"\b(impact|consequence|effect|risk)", re.I), Operation.ASSESS_IMPACT),
    (re.compile(r"\b(evidence|source|support|cite)", re.I), Operation.RETRIEVE_EVIDENCE),
    (re.compile(r"\b(verify|verif|confirm|check)", re.I), Operation.VERIFY_FINDINGS),
    (re.compile(r"\b(summar)", re.I), Operation.SUMMARIZE),
]

# An objective this short with no interrogative content cannot be planned against.
_VAGUE = re.compile(
    r"^\s*(look at|check|review|see|read|analyse|analyze|examine)\s+"
    r"(these|those|the|my|this)?\s*(files?|documents?|reports?|them|it)\s*[.!]?\s*$",
    re.I,
)


def map_operation(raw: str) -> Operation | None:
    """Map a model-supplied operation name onto the closed vocabulary.

    Returns None when there is no match, which is what turns an invented operation into a
    visible `UnsupportedOperation` rather than a silent omission.
    """
    key = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    if not key:
        return None
    try:
        return Operation(key)
    except ValueError:
        return _SYNONYMS.get(key)


def derive_operations(objective: Objective) -> set[Operation]:
    """Deterministic pre-pass: what the request structurally implies.

    Runs before the model so it is never the only signal. Cheap, explainable, and stable
    across models — which matters when Experiment 001 swaps the model out.
    """
    found: set[Operation] = set()
    text = objective.text

    for pattern, operation in _KEYWORDS:
        if pattern.search(text):
            found.add(operation)

    docs = objective.scope.documents
    if docs:
        found.add(Operation.PROCESS_DOCUMENTS)
    if any(d.kind is DocumentKind.CSV for d in docs):
        found.add(Operation.EXTRACT_BUDGET)

    # Any real investigation ends in a report.
    if found:
        found.add(Operation.GENERATE_REPORT)

    return found


def looks_vague(objective: Objective) -> bool:
    """Whether the objective states no answerable question."""
    return bool(_VAGUE.match(objective.text.strip()))


class IntentEngine:
    """Turns an `Objective` into a validated `Intent`."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def analyze(self, objective: Objective, *, emit: object | None = None) -> Intent:
        heuristic_ops = derive_operations(objective)

        candidate = await self._ask_model(objective, emit=emit)
        intent = self._build(objective, candidate, heuristic_ops)

        if emit is not None:
            emitter = getattr(emit, "emit", None)
            if emitter is not None:
                await emitter(
                    EventType.INTENT_CREATED,
                    payload={
                        "goal": intent.goal,
                        "operations": [op.value for op in intent.operations],
                        "unsupported": [u.requested for u in intent.unsupported_operations],
                        "clarification_needed": intent.clarification_needed,
                    },
                )
        return intent

    async def _ask_model(self, objective: Objective, *, emit: object | None) -> CandidateIntent:
        prompt = self._prompts.get("intent").render(
            objective=objective.text,
            documents=self._describe_documents(objective),
            operations="\n".join(f"- {op.value}" for op in Operation),
        )
        try:
            return await generate_structured(
                self._provider,
                CandidateIntent,
                prompt,
                role="intent",
                emit=emit,
            )
        except StructuredOutputError as exc:
            # Degrade to the deterministic pre-pass rather than failing the run. The
            # heuristics alone give a usable, if coarser, intent - and the shortfall is
            # recorded rather than hidden.
            log.warning("intent_model_failed_degrading_to_heuristics", role=exc.role)
            return CandidateIntent(clarification_needed=False)

    @staticmethod
    def _describe_documents(objective: Objective) -> str:
        docs = objective.scope.documents
        if not docs:
            return "(none supplied)"
        return "\n".join(f"- {d.name} ({d.kind.value})" for d in docs)

    def _build(
        self,
        objective: Objective,
        candidate: CandidateIntent,
        heuristic_ops: set[Operation],
    ) -> Intent:
        mapped: list[Operation] = []
        unsupported: list[UnsupportedOperation] = []

        for raw in candidate.operations:
            operation = map_operation(raw)
            if operation is None:
                unsupported.append(
                    UnsupportedOperation(
                        requested=raw,
                        reason="not in the system's operation vocabulary",
                    )
                )
            elif operation not in mapped:
                mapped.append(operation)

        for raw in candidate.unsupported:
            if raw.strip():
                unsupported.append(
                    UnsupportedOperation(
                        requested=raw, reason="reported unsupported by the analyser"
                    )
                )

        # Union with the deterministic pre-pass. The model may miss something structurally
        # obvious; the heuristics may miss something only a reader would catch.
        for operation in sorted(heuristic_ops, key=lambda o: o.value):
            if operation not in mapped:
                mapped.append(operation)

        if not mapped:
            mapped = [Operation.SUMMARIZE, Operation.GENERATE_REPORT]

        vague = candidate.clarification_needed or looks_vague(objective)
        question = candidate.clarification_question.strip()
        if vague and not question:
            question = (
                "What specifically should be investigated in these documents - "
                "for example a consistency check, a comparison, or a summary?"
            )

        return Intent(
            goal=candidate.goal.strip() or self._fallback_goal(mapped),
            objective=candidate.objective.strip() or objective.text[:200],
            required_operations=[
                # Supporting operations are recorded but not made mandatory: the objective
                # did ask for them, and the pipeline does them - just not as planned tasks.
                RequiredOperation(operation=op, optional=op in SUPPORTING_OPERATIONS)
                for op in mapped
            ],
            unsupported_operations=unsupported,
            constraints=Constraints(evidence_required=candidate.evidence_required),
            output_format=self._map_format(candidate.output_format),
            clarification_needed=vague,
            clarification_question=question if vague else "",
        )

    @staticmethod
    def _fallback_goal(operations: list[Operation]) -> str:
        if Operation.DETECT_CONTRADICTIONS in operations:
            return "investigate_contradictions"
        if Operation.DETECT_INCONSISTENCIES in operations:
            return "investigate_inconsistencies"
        if Operation.COMPARE_SOURCES in operations:
            return "compare_sources"
        return "investigate_documents"

    @staticmethod
    def _map_format(raw: str) -> OutputFormat:
        try:
            return OutputFormat(re.sub(r"[^a-z_]+", "_", raw.strip().lower()))
        except ValueError:
            return OutputFormat.INVESTIGATION_REPORT


def model_role_is_configured() -> bool:
    """Guard used by the CLI to fail early with a clear message."""
    return "intent" in get_models_config().roles
