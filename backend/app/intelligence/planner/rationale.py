"""Why each task is in the plan, and which workstream it belongs to (Phase 49).

A plan is only followable if every step says why it is there. The reason comes from what put the
task in the plan, never from a model:

- **the objective** - the required operations the task implements ("the objective asks to
  compare_sources");
- **a repair** - a step the planner left out and the system added (BUG-035), or the report step
  every plan must end in;
- **an evidence gap** - a task the replanning loop inserted to find a specific missing piece;
- **the knowledge pass** - the step that reads every document into the knowledge graph;
- otherwise, what the task type is for (a test fails if a type has no such sentence).

Workstreams group the tasks the way a person would read a plan: gather, extract, analyse, report,
and the gaps the run went back for.
"""

from __future__ import annotations

from app.schemas.intent import Intent
from app.schemas.task import TASK_SATISFIES, Task, TaskType

GATHER = "Gather the evidence"
EXTRACT = "Extract what the documents state"
ANALYSE = "Analyse and compare"
REPORT = "Verify and report"
GAPS = "Close evidence gaps"

WORKSTREAMS: dict[TaskType, str] = {
    TaskType.PROCESS_DOCUMENTS: GATHER,
    TaskType.RETRIEVE_EVIDENCE: GATHER,
    TaskType.EXTRACT_TIMELINE: EXTRACT,
    TaskType.EXTRACT_BUDGET: EXTRACT,
    TaskType.EXTRACT_MILESTONES: EXTRACT,
    TaskType.EXTRACT_ENTITIES: EXTRACT,
    TaskType.EXTRACT_CLAIMS: EXTRACT,
    TaskType.NORMALIZE_DATES: ANALYSE,
    TaskType.NORMALIZE_VALUES: ANALYSE,
    TaskType.COMPARE_SOURCES: ANALYSE,
    TaskType.DETECT_INCONSISTENCIES: ANALYSE,
    TaskType.CALCULATE_DIFFERENCE: ANALYSE,
    TaskType.ASSESS_IMPACT: ANALYSE,
    TaskType.VERIFY_FINDINGS: REPORT,
    TaskType.SUMMARIZE: REPORT,
    TaskType.SYNTHESIZE: REPORT,
}

# What each task type is for, when nothing more specific put it in the plan.
PURPOSE: dict[TaskType, str] = {
    TaskType.PROCESS_DOCUMENTS: "reads the attached documents so later steps have text to work on",
    TaskType.RETRIEVE_EVIDENCE: "finds the passages that bear on the question",
    TaskType.EXTRACT_TIMELINE: "collects the dates, so they can be compared",
    TaskType.EXTRACT_BUDGET: "collects the budget and spending figures, so they can be compared",
    TaskType.EXTRACT_MILESTONES: "collects the milestones and their dates",
    TaskType.EXTRACT_ENTITIES: "identifies who and what the documents are about",
    TaskType.EXTRACT_CLAIMS: "records what each source states, so sources can be set side by side",
    TaskType.NORMALIZE_DATES: "puts dates in one form, so equal dates compare as equal",
    TaskType.NORMALIZE_VALUES: "puts amounts in one form, so equal amounts compare as equal",
    TaskType.COMPARE_SOURCES: "sets the sources against each other",
    TaskType.DETECT_INCONSISTENCIES: "looks for values that cannot both be true",
    TaskType.CALCULATE_DIFFERENCE: "works out the difference between figures",
    TaskType.ASSESS_IMPACT: "weighs what the findings mean for the question",
    TaskType.VERIFY_FINDINGS: "checks each finding against its evidence",
    TaskType.SUMMARIZE: "summarises what was established",
    TaskType.SYNTHESIZE: "writes the report from what was established",
}


def rationale_for(task: Task, intent: Intent | None) -> str:
    """The reason a planned task is in the plan, from the objective's operations or its type."""
    if intent is not None:
        asked = [
            op.value for op in intent.operations if op in TASK_SATISFIES.get(task.task_type, set())
        ]
        if asked:
            return f"the objective asks to {', '.join(asked)}; this {PURPOSE[task.task_type]}"
    return f"this {PURPOSE[task.task_type]}"


def annotate(tasks: list[Task], intent: Intent | None) -> None:
    """Give every task without one its rationale and workstream, in place. Tasks that already say
    why (a repair, a gap, the knowledge pass) keep their reason."""
    for task in tasks:
        if not task.rationale:
            task.rationale = rationale_for(task, intent)
        if not task.workstream:
            task.workstream = GAPS if task.created_for_gap_id else WORKSTREAMS[task.task_type]
