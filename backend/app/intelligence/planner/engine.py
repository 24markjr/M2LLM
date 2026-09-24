"""The planner — intent to a validated, executable DAG.

The model generates a candidate decomposition. Application code then validates it, repairs
what is deterministically repairable, and re-prompts a bounded number of times. If it still
will not produce a legal plan, the run fails cleanly with `PLAN_INVALID` rather than
executing something malformed.

That split is the difference between "an LLM wrote some steps" and "the agent produces a
valid executable plan".
"""

from __future__ import annotations

from pydantic import Field

from app.core.agent_config import get_agent_bounds
from app.core.logging import get_logger
from app.intelligence.planner.validator import repair, validate
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.event import EventType
from app.schemas.intent import Intent
from app.schemas.objective import Objective
from app.schemas.plan import Plan, PlanValidationResult
from app.schemas.task import TASK_SATISFIES, Task, TaskType

log = get_logger(__name__)


class PlanInvalidError(RuntimeError):
    """The model could not produce a legal plan within its budget.

    A clean failure. Executing an invalid plan is never an option: a cycle would hang the
    scheduler, and an uncovered operation would produce a report missing half the request
    with nothing to indicate it.
    """

    def __init__(self, result: PlanValidationResult) -> None:
        codes = ", ".join(v.code.value for v in result.violations)
        super().__init__(f"plan failed validation: {codes}")
        self.result = result


class CandidateTask(JarvisModel):
    """One task as the model proposes it. Types are strings until validated."""

    id: str = ""
    type: str = ""
    description: str = ""
    depends_on: list[str] = Field(default_factory=list)


class CandidatePlan(JarvisModel):
    tasks: list[CandidateTask] = Field(default_factory=list)


# Task-type phrasings that map onto the closed vocabulary, mirroring `_SYNONYMS` in the intent
# engine and for the same reason: small and explicit, never fuzzy. A fuzzy matcher would
# reintroduce the silent nearest-match problem the closed vocabulary exists to prevent.
#
# Measured: this model proposes `detect_contradictions` persistently. The task was dropped,
# which left `detect_inconsistencies` uncovered, which failed the plan - so an objective about
# finding contradictions could not be planned at all because of one word.
_TASK_TYPE_SYNONYMS: dict[str, TaskType] = {
    "detect_contradictions": TaskType.DETECT_INCONSISTENCIES,
    "find_contradictions": TaskType.DETECT_INCONSISTENCIES,
    "identify_contradictions": TaskType.DETECT_INCONSISTENCIES,
    "detect_conflicts": TaskType.DETECT_INCONSISTENCIES,
    "compare_documents": TaskType.COMPARE_SOURCES,
    "cross_reference": TaskType.COMPARE_SOURCES,
    "extract_dates": TaskType.EXTRACT_TIMELINE,
    "extract_financials": TaskType.EXTRACT_BUDGET,
    "extract_costs": TaskType.EXTRACT_BUDGET,
    "gather_evidence": TaskType.RETRIEVE_EVIDENCE,
    "write_report": TaskType.SYNTHESIZE,
    "generate_report": TaskType.SYNTHESIZE,
    "summarise": TaskType.SUMMARIZE,
}


def coerce_task_type(proposed: str) -> TaskType | None:
    """Map a proposed task type onto the vocabulary, or return None if it is not in it."""
    normalised = proposed.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return TaskType(normalised)
    except ValueError:
        return _TASK_TYPE_SYNONYMS.get(normalised)


class Planner:
    """Produces a validated `Plan`, or fails cleanly."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def create_plan(
        self,
        intent: Intent,
        objective: Objective,
        *,
        emit: object | None = None,
        max_reprompts: int = 2,
    ) -> Plan:
        bounds = get_agent_bounds()
        last: PlanValidationResult | None = None
        feedback = ""

        for attempt in range(max_reprompts + 1):
            candidate = await self._ask_model(intent, objective, feedback, emit=emit)
            tasks = self._to_tasks(candidate)

            tasks, dependencies, repairs = repair(tasks, bounds.max_plan_tasks)
            result = validate(
                tasks, intent, max_tasks=bounds.max_plan_tasks, reprompt_count=attempt
            )
            result = result.model_copy(update={"repairs": repairs})
            last = result

            if result.valid:
                plan = Plan(tasks=tasks, dependencies=dependencies, validation=result)
                await self._emit_plan(plan, emit)
                return plan

            log.warning(
                "plan_invalid",
                attempt=attempt + 1,
                of=max_reprompts + 1,
                violations=[v.code.value for v in result.violations],
            )
            # Tell the model exactly what was wrong. The same principle as the structured
            # output repair loop: specific errors fix far more than "try again".
            feedback = "\n".join(f"- {v.message}" for v in result.violations)

        assert last is not None
        raise PlanInvalidError(last)

    async def _ask_model(
        self,
        intent: Intent,
        objective: Objective,
        feedback: str,
        *,
        emit: object | None,
    ) -> CandidatePlan:
        bounds = get_agent_bounds()
        prompt = self._prompts.get("planner").render(
            objective=objective.text,
            operations="\n".join(f"- {op.value}" for op in intent.mandatory_operations),
            task_types="\n".join(self._describe_task_type(t) for t in TaskType),
            documents="\n".join(f"- {d.name}" for d in objective.scope.documents)
            or "(none supplied)",
            max_tasks=bounds.max_plan_tasks,
        )
        if feedback:
            prompt = (
                f"{prompt}\n\n"
                "Your previous plan was rejected for these reasons:\n"
                f"{feedback}\n\n"
                "Produce a corrected plan."
            )

        try:
            return await generate_structured(
                self._provider, CandidatePlan, prompt, role="planner", emit=emit
            )
        except StructuredOutputError:
            log.warning("planner_structured_output_failed")
            return CandidatePlan()

    @staticmethod
    def _describe_task_type(task_type: TaskType) -> str:
        """One catalogue line, so the model plans against operations that really exist."""
        satisfies = sorted(TASK_SATISFIES.get(task_type, set()), key=lambda o: o.value)
        names = ", ".join(o.value for o in satisfies)
        return f"- {task_type.value} (satisfies: {names})"

    @staticmethod
    def _to_tasks(candidate: CandidatePlan) -> list[Task]:
        """Convert proposed tasks to typed ones, dropping any with an unknown type.

        A dropped task usually leaves an operation uncovered, which the validator then
        reports - so an invented task type surfaces as a specific violation rather than
        vanishing.
        """
        tasks: list[Task] = []
        renumber: dict[str, str] = {}

        for index, proposed in enumerate(candidate.tasks, start=1):
            task_type = coerce_task_type(proposed.type)
            if task_type is None:
                log.warning("planner_invented_task_type", proposed=proposed.type)
                continue
            new_id = f"task_{index:03d}"
            renumber[proposed.id or new_id] = new_id
            tasks.append(
                Task(
                    task_id=new_id,
                    task_type=task_type,
                    description=proposed.description or task_type.value,
                    depends_on=[],
                )
            )

        # Second pass: dependencies are remapped once every id is known.
        for task, proposed in zip(tasks, [c for c in candidate.tasks if _typed(c)], strict=False):
            task.depends_on = [
                renumber[d]
                for d in proposed.depends_on
                if d in renumber and renumber[d] != task.task_id
            ]

        return tasks

    @staticmethod
    async def _emit_plan(plan: Plan, emit: object | None) -> None:
        if emit is None:
            return
        emitter = getattr(emit, "emit", None)
        if emitter is None:
            return
        await emitter(
            EventType.PLAN_CREATED,
            payload={
                "task_count": len(plan.tasks),
                "edge_count": len(plan.dependencies),
                "clean": plan.validation.clean if plan.validation else False,
                "repairs": [r.action.value for r in plan.validation.repairs]
                if plan.validation
                else [],
            },
        )
        await emitter(
            EventType.TASK_GRAPH_CREATED,
            payload={"tasks": [t.task_id for t in plan.tasks]},
        )


def _typed(candidate: CandidateTask) -> bool:
    try:
        TaskType(candidate.type.strip().lower().replace(" ", "_"))
    except ValueError:
        return False
    return True


def execution_levels(plan: Plan) -> list[list[str]]:
    """Group tasks into waves that can run concurrently.

    Level 0 is everything with no dependencies; level N is everything whose dependencies all
    sit in earlier levels. This is what the execution engine will schedule (Phase 11), and
    what makes the parallelism in a plan visible rather than theoretical.
    """
    remaining = {t.task_id: set(t.depends_on) for t in plan.tasks}
    levels: list[list[str]] = []
    done: set[str] = set()

    while remaining:
        ready = sorted(tid for tid, deps in remaining.items() if deps <= done)
        if not ready:
            break  # a cycle survived validation; caller reports it
        levels.append(ready)
        done |= set(ready)
        for tid in ready:
            remaining.pop(tid)

    return levels
