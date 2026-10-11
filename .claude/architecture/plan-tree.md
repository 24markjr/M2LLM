# Visible adaptive planning (Phase 49)

Every task says why it is in the plan, the plan reads as a tree, and every change the run made to
it is shown with its trigger and reason.

## Why each task is there (`intelligence/planner/rationale.py`)

`Task.rationale` and `Task.workstream`, set from what put the task in the plan - never by a model:

| Origin | Rationale |
|---|---|
| the planner | "the objective asks to compare_sources; this sets the sources against each other" (the intent's operations the task type implements), or the type's purpose |
| a repair | "added by a repair: every plan must end in its report"; "added by a repair: the objective requires detect_inconsistencies and the planner left it out on every attempt" (BUG-035) |
| the replanning loop | "inserted by the replanning loop to close gap G-001: <what was missing>" |
| the knowledge pass | "added by the orchestrator: reads every document into the knowledge graph..." |

Workstreams: Gather the evidence, Extract what the documents state, Analyse and compare, Close
evidence gaps, Verify and report. Invariant (tested): every task type has a purpose and a workstream,
and every task in a plan has a rationale - `annotate` runs when the planner returns a plan and again
after the loop, so no path leaves one without.

Revisions now snapshot the plan: `PlanRevision.tasks_before` and `tasks_after`.

## The tree (`app/api/plan_tree.py`)

`GET /api/v1/missions/{id}/plan`: objective -> workstreams -> steps (label, why, inputs - the steps
it consumed, or the documents - action (tool), output (what it observed), dependencies, status,
the revision that added it); `changes` (revision, trigger, reason, the gap that triggered it, the
steps added with their why, before -> after counts); `repairs` (how the plan was made valid). Also
in the replay snapshot. `TaskNode` (the task graph) carries rationale and workstream too.

Console: the plan tree in the technical view; "JARVIS changed its plan" in both views.

Nothing here touches what the model is asked, so the evaluation baseline is unchanged.
