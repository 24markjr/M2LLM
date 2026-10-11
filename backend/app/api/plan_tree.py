"""The plan tree (Phase 49): objective -> workstreams -> steps, and every change the run made.

Built from the executed graph, so tasks the replanning loop inserted are in it, and from the run's
revisions, so each change says what triggered it and why. Inputs are the steps a task consumed (or
the documents, for a step that reads them); the output is what the task observed.
"""

from __future__ import annotations

from app.api.v1.schemas import PlanChange, PlanStep, PlanTree, PlanWorkstream
from app.intelligence.planner.rationale import ANALYSE, EXTRACT, GAPS, GATHER, REPORT
from app.orchestration.labels import step_label
from app.orchestration.mission import MissionResult
from app.schemas.task import Task

ORDER = [GATHER, EXTRACT, ANALYSE, GAPS, REPORT]


def _step(
    task: Task, labels: dict[str, str], outputs: dict[str, str], documents: list[str]
) -> PlanStep:
    inputs = [f"{dep} {labels.get(dep, '')}".strip() for dep in task.depends_on] or (
        [f"the documents ({len(documents)})"] if documents else []
    )
    return PlanStep(
        task_id=task.task_id,
        label=step_label(task.task_type, task.status),
        task_type=task.task_type.value,
        why=task.rationale or "no reason recorded",
        inputs=inputs,
        action=task.selection.tool_name if task.selection else "",
        output=outputs.get(task.task_id, ""),
        depends_on=list(task.depends_on),
        status=task.status,
        inserted_by_revision=task.created_by_revision,
    )


def plan_tree(run_id: str, result: MissionResult) -> PlanTree:
    assert result.plan is not None
    tasks = result.plan.tasks
    documents = [d.name for d in result.objective.scope.documents]
    labels = {t.task_id: step_label(t.task_type, t.status) for t in tasks}
    outputs: dict[str, str] = {}
    for observation in result.observations:
        outputs.setdefault(observation.task_id, observation.content[:240])
    steps = {t.task_id: _step(t, labels, outputs, documents) for t in tasks}

    grouped: dict[str, list[PlanStep]] = {}
    for task in tasks:
        grouped.setdefault(task.workstream or ANALYSE, []).append(steps[task.task_id])
    names = [n for n in ORDER if n in grouped] + [n for n in grouped if n not in ORDER]

    changes = [
        PlanChange(
            revision=revision.revision,
            trigger=revision.trigger.value,
            reason=revision.reason,
            triggered_by=revision.triggered_by_id,
            added=[steps[t] for t in revision.added_task_ids if t in steps],
            skipped=list(revision.skipped_task_ids),
            tasks_before=len(revision.tasks_before),
            tasks_after=len(revision.tasks_after),
        )
        for revision in result.revisions
    ]
    validation = result.plan.validation
    repairs = [r.detail for r in validation.repairs] if validation is not None else []
    return PlanTree(
        run_id=run_id,
        objective=result.objective.text,
        workstreams=[PlanWorkstream(name=n, steps=grouped[n]) for n in names],
        changes=changes,
        repairs=repairs,
    )
