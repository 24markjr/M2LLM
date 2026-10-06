/**
 * Cases and the Professional view (Phase 44), the pure part: links, and turning a run's tasks and
 * findings into what a person follows - steps in plain words and the conclusion so far.
 */

import type { Finding, TaskNode } from "../api/types";

export const CASE_ID = /^CASE-\d{4}-\d{5,}$/;
export const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export const CASE_STATUSES = ["OPEN", "INVESTIGATING", "REVIEW", "CLOSED"] as const;

export function caseLink(caseId?: string): string {
  return caseId && CASE_ID.test(caseId) ? `#/case/${caseId}` : "#/";
}

export function caseIdFromHash(hash: string): string {
  const match = /^#\/case\/(CASE-\d{4}-\d{5,})$/.exec(hash.split("?")[0] ?? hash);
  return match?.[1] ?? "";
}

export type StepState = "done" | "doing" | "todo" | "failed" | "skipped";

export interface Step {
  id: string;
  label: string;
  state: StepState;
  /** Inserted by the replanning loop: the plan changed while it ran. */
  added: boolean;
}

const STATE: Record<string, StepState> = {
  COMPLETED: "done",
  RUNNING: "doing",
  RETRYING: "doing",
  FAILED: "failed",
  BLOCKED: "failed",
  SKIPPED: "skipped",
};

/** The run's tasks as steps a person reads, in plan order. The label comes from the engine. */
export function stepsFrom(nodes: TaskNode[]): Step[] {
  return nodes.map((node) => ({
    id: node.task_id,
    label: node.label || node.description || node.task_type,
    state: STATE[node.status] ?? "todo",
    added: node.inserted_by_replan,
  }));
}

export const STEP_MARK: Record<StepState, string> = {
  done: "✓",
  doing: "↻",
  todo: "·",
  failed: "✗",
  skipped: "–",
};

/**
 * The conclusion so far: what passed independent verification. Unverified and rejected claims are
 * not conclusions, and saying nothing is the honest answer when nothing passed.
 */
export function conclusion(findings: Finding[], finished: boolean): string[] {
  const verified = findings.filter((f) => f.verification?.status === "SUPPORTED").map((f) => f.claim);
  if (verified.length) return verified;
  if (!finished) return [];
  return findings.length
    ? ["Nothing passed independent verification; the findings below are what was claimed and how each check went."]
    : ["Nothing was established. On a question with nothing to find, that is the correct answer."];
}
