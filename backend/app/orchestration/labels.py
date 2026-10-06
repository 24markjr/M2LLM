"""Plain-language step labels for the Professional view (Phase 44).

A person following an investigation should read "Cross-checked the sources against each other",
not `task_004 compare_sources COMPLETED`. Each task type has three phrasings - to do, doing, done -
and the status picks one. Deterministic, never written by a model: the label describes what the
task type does, so it cannot overstate what a run did.

Every task type must have a label; a test fails when a new type is added without one.
"""

from __future__ import annotations

from app.schemas.task import TaskStatus, TaskType

# (to do, doing, done)
LABELS: dict[TaskType, tuple[str, str, str]] = {
    TaskType.PROCESS_DOCUMENTS: (
        "Read the documents",
        "Reading the documents",
        "Read the documents",
    ),
    TaskType.EXTRACT_TIMELINE: (
        "Extract the dates and timeline",
        "Extracting the dates and timeline",
        "Extracted the dates and timeline",
    ),
    TaskType.EXTRACT_BUDGET: (
        "Extract the budget and spending figures",
        "Extracting the budget and spending figures",
        "Extracted the budget and spending figures",
    ),
    TaskType.EXTRACT_MILESTONES: (
        "Extract the milestones",
        "Extracting the milestones",
        "Extracted the milestones",
    ),
    TaskType.EXTRACT_ENTITIES: (
        "Identify the people, organisations and things involved",
        "Identifying the people, organisations and things involved",
        "Identified the people, organisations and things involved",
    ),
    TaskType.EXTRACT_CLAIMS: (
        "Build the knowledge graph of what each source states",
        "Building the knowledge graph of what each source states",
        "Built the knowledge graph of what each source states",
    ),
    TaskType.NORMALIZE_DATES: (
        "Put the dates in one form",
        "Putting the dates in one form",
        "Put the dates in one form",
    ),
    TaskType.NORMALIZE_VALUES: (
        "Put the amounts in one form",
        "Putting the amounts in one form",
        "Put the amounts in one form",
    ),
    TaskType.COMPARE_SOURCES: (
        "Cross-check the sources against each other",
        "Cross-checking the sources against each other",
        "Cross-checked the sources against each other",
    ),
    TaskType.DETECT_INCONSISTENCIES: (
        "Look for contradictions",
        "Looking for contradictions",
        "Looked for contradictions",
    ),
    TaskType.CALCULATE_DIFFERENCE: (
        "Calculate the differences",
        "Calculating the differences",
        "Calculated the differences",
    ),
    TaskType.ASSESS_IMPACT: (
        "Assess the impact",
        "Assessing the impact",
        "Assessed the impact",
    ),
    TaskType.RETRIEVE_EVIDENCE: (
        "Find the supporting evidence",
        "Finding the supporting evidence",
        "Found the supporting evidence",
    ),
    TaskType.VERIFY_FINDINGS: (
        "Verify the findings independently",
        "Verifying the findings independently",
        "Verified the findings independently",
    ),
    TaskType.SUMMARIZE: (
        "Summarise what was found",
        "Summarising what was found",
        "Summarised what was found",
    ),
    TaskType.SYNTHESIZE: (
        "Bring the evidence together",
        "Bringing the evidence together",
        "Brought the evidence together",
    ),
}


def step_label(task_type: TaskType, status: TaskStatus) -> str:
    """The step as a person reads it, in the tense its status calls for."""
    to_do, doing, done = LABELS.get(task_type, (task_type.value, task_type.value, task_type.value))
    if status is TaskStatus.COMPLETED:
        return done
    if status in {TaskStatus.RUNNING, TaskStatus.RETRYING}:
        return doing
    if status is TaskStatus.FAILED:
        return f"Could not {to_do[0].lower()}{to_do[1:]}"
    if status is TaskStatus.BLOCKED:
        return f"Blocked: {to_do[0].lower()}{to_do[1:]}"
    if status is TaskStatus.SKIPPED:
        return f"Skipped: {to_do[0].lower()}{to_do[1:]}"
    return to_do
