"""The tool router — deciding which capability accomplishes a task.

Three stages, and the ordering is the design:

1. **Capability filter** (deterministic). The task type declares the capability it needs;
   only tools serving it survive.
2. **Schema compatibility** (deterministic). Can the task's inputs actually satisfy the
   tool's required fields?
3. **LLM tiebreak** — *only* when two or more candidates remain.

Why deterministic first: it makes tool-selection accuracy measurable and largely
model-independent. If the model chose every time, the Phase 20 metric would be measuring the
model rather than the system, and it would move for reasons nobody could attribute.

The mode of every selection is recorded. A rising share of `LLM_TIEBREAK` means the
capability model has grown too coarse to discriminate — a design signal worth being able to
see.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.errors import StructuredOutputError
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.event import EventType
from app.schemas.task import Task
from app.schemas.tool import SelectionMode, ToolCapability, ToolSelection
from app.tools.base import Tool, ToolRegistry

log = get_logger(__name__)


class NoCapableToolError(RuntimeError):
    """Nothing registered can serve this task.

    The task is skipped with a recorded reason rather than silently dropped: a dropped task
    produces a finding with invisibly missing support, which is the failure mode this whole
    architecture exists to prevent.
    """

    def __init__(self, task: Task) -> None:
        super().__init__(f"no tool serves {task.required_capability.value} for {task.task_id}")
        self.task = task


class TiebreakChoice(JarvisModel):
    """What the model returns when it has to break a tie."""

    tool_name: str = ""
    reason: str = ""


class ToolRouter:
    """Selects a tool for a task, and records why."""

    def __init__(self, registry: ToolRegistry, provider: LLMProvider | None = None) -> None:
        self._registry = registry
        self._provider = provider

    async def route(self, task: Task, *, emit: object | None = None) -> ToolSelection:
        capability = task.required_capability

        # Stage 1: capability filter.
        candidates = self._registry.serving(capability)
        if not candidates:
            raise NoCapableToolError(task)

        # Stage 2: schema compatibility.
        compatible = [t for t in candidates if self._compatible(t, task)]
        if compatible:
            candidates = compatible

        if len(candidates) == 1:
            selection = ToolSelection(
                tool_name=candidates[0].name,
                capability=capability,
                mode=SelectionMode.DETERMINISTIC,
                reason=f"only registered tool serving {capability.value}",
                confidence=1.0,
            )
        else:
            selection = await self._tiebreak(task, capability, candidates)

        await self._emit(task, selection, emit)
        return selection

    def _compatible(self, tool: Tool, task: Task) -> bool:
        """Whether the task's inputs can satisfy the tool's required fields.

        A structural check, not a guess: a tool whose required inputs the task cannot provide
        is not a candidate however well its description reads.
        """
        schema = tool.input_schema.model_json_schema()
        required = set(schema.get("required", []))
        if not required:
            return True
        available = set(task.inputs) | {"query", "document_ids", "scope"}
        return required <= available

    async def _tiebreak(
        self, task: Task, capability: ToolCapability, candidates: list[Tool]
    ) -> ToolSelection:
        names = [t.name for t in candidates]

        # Cheapest-first is the deterministic fallback when no model is available, and the
        # default the model has to argue against.
        cheapest = min(candidates, key=lambda t: _COST_ORDER[t.cost_hint.value])

        if self._provider is None:
            return ToolSelection(
                tool_name=cheapest.name,
                capability=capability,
                mode=SelectionMode.FALLBACK,
                reason="no provider available; chose the lowest-cost candidate",
                alternatives_considered=names,
                confidence=0.6,
            )

        catalogue = "\n".join(
            f"- {t.name} (cost={t.cost_hint.value}): {t.description}" for t in candidates
        )
        prompt = (
            "Select the single best tool for this task.\n\n"
            f"Task type: {task.task_type.value}\n"
            f"Task description: {task.description}\n"
            f"Required capability: {capability.value}\n\n"
            f"Candidate tools:\n{catalogue}\n\n"
            "Prefer the lower-cost tool when both would work. "
            "Return the tool name exactly as written above."
        )

        try:
            choice = await generate_structured(
                self._provider, TiebreakChoice, prompt, role="router"
            )
        except StructuredOutputError:
            log.warning("router_tiebreak_failed", task_id=task.task_id)
            return ToolSelection(
                tool_name=cheapest.name,
                capability=capability,
                mode=SelectionMode.FALLBACK,
                reason="tiebreak failed; chose the lowest-cost candidate",
                alternatives_considered=names,
                confidence=0.5,
            )

        chosen = choice.tool_name.strip()
        if chosen not in names:
            # The model named something that is not a candidate. Fall back rather than
            # trusting it - an unregistered tool name would fail at dispatch.
            log.warning("router_chose_unknown_tool", proposed=chosen, task_id=task.task_id)
            return ToolSelection(
                tool_name=cheapest.name,
                capability=capability,
                mode=SelectionMode.FALLBACK,
                reason=f"tiebreak named an unavailable tool '{chosen}'; used lowest cost",
                alternatives_considered=names,
                confidence=0.5,
            )

        return ToolSelection(
            tool_name=chosen,
            capability=capability,
            mode=SelectionMode.LLM_TIEBREAK,
            reason=choice.reason or "selected by tiebreak",
            alternatives_considered=names,
            confidence=0.8,
        )

    @staticmethod
    async def _emit(task: Task, selection: ToolSelection, emit: object | None) -> None:
        if emit is None:
            return
        emitter = getattr(emit, "emit", None)
        if emitter is None:
            return
        await emitter(
            EventType.TOOL_SELECTED,
            payload={
                "tool": selection.tool_name,
                "capability": selection.capability.value,
                "mode": selection.mode.value,
                "reason": selection.reason,
                "alternatives": selection.alternatives_considered,
            },
            task_id=task.task_id,
            tool_name=selection.tool_name,
        )


_COST_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
