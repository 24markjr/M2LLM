/**
 * What a running investigation is doing, in one line (demo readiness): the screen must never look
 * frozen while a step takes a minute. Read from the run's own events - nothing is guessed.
 */

import type { EventRecord } from "../api/types";

const DOING: Record<string, string> = {
  RUN_STARTED: "Starting",
  INJECTION_DETECTED: "Screening the files for hidden instructions",
  INTENT_CREATED: "Understood the question; planning the work",
  PLAN_CREATED: "Plan made; starting the work",
  TASK_GRAPH_CREATED: "Plan made; starting the work",
  KNOWLEDGE_EXTRACTED: "Built the knowledge graph; working through the plan",
  TASK_STARTED: "Working through the plan",
  TOOL_EXECUTED: "Reading the evidence",
  OBSERVATION_RECORDED: "Reading the evidence",
  REASONING_STARTED: "Reasoning over what it read",
  FINDING_CREATED: "Drafting findings",
  VERIFICATION_STARTED: "Checking each finding against the lines it cites",
  FINDING_VERIFIED: "Checking each finding against the lines it cites",
  FINDING_REJECTED: "Checking each finding against the lines it cites",
  EVIDENCE_GAP_DETECTED: "Looking for the evidence still missing",
  REPLAN_STARTED: "Looking for the evidence still missing",
  HYPOTHESES_EVALUATED: "Weighing competing explanations",
  SYNTHESIS_STARTED: "Writing the report",
  BUDGET_WARNING: "Time limit reached - finishing with what it has established",
};

export interface Progress {
  doing: string;
  steps: number;
  tasksDone: number;
  tasksTotal: number;
  verified: number;
  rejected: number;
}

export function progressOf(events: EventRecord[], tasksTotal: number): Progress {
  let doing = "Waiting for a free slot";
  let steps = 0;
  let tasksDone = 0;
  let verified = 0;
  let rejected = 0;
  for (const event of events) {
    const label = DOING[event.event_type];
    if (label) doing = label;
    if (event.event_type === "LLM_CALL_COMPLETED") steps += 1;
    if (event.event_type === "TASK_COMPLETED" || event.event_type === "TASK_SKIPPED") tasksDone += 1;
    if (event.event_type === "FINDING_VERIFIED") verified += 1;
    if (event.event_type === "FINDING_REJECTED") rejected += 1;
  }
  return { doing, steps, tasksDone, tasksTotal, verified, rejected };
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function progressLine(progress: Progress, elapsedS: number): string {
  const parts = [progress.doing, `${clock(elapsedS)} elapsed`, `${progress.steps} model step(s)`];
  if (progress.tasksTotal) parts.push(`${Math.min(progress.tasksDone, progress.tasksTotal)} of ${progress.tasksTotal} tasks`);
  if (progress.verified || progress.rejected) parts.push(`${progress.verified} verified, ${progress.rejected} rejected`);
  return parts.join(" · ");
}
