/** The plan tree as the console shows it (Phase 49). Pure, so it is tested without rendering. */

import type { PlanChange, PlanTree } from "../api/types";

/** "JARVIS changed its plan": one sentence per change, with its trigger and size. */
export function changeHeadline(change: PlanChange): string {
  const trigger = change.trigger.replace(/_/g, " ").toLowerCase();
  const added = change.added.length;
  const skipped = change.skipped.length;
  const parts = [
    added ? `added ${added} step(s)` : "",
    skipped ? `skipped ${skipped}` : "",
  ].filter(Boolean);
  return `Revision ${change.revision} (${trigger}${change.triggered_by ? ` ${change.triggered_by}` : ""}): ${parts.join(", ")} - ${change.tasks_before} → ${change.tasks_after} steps. ${change.reason}`;
}

/** Steps in the tree, and how many the run added after planning. */
export function planCounts(tree: PlanTree): { steps: number; added: number } {
  const steps = tree.workstreams.reduce((n, w) => n + w.steps.length, 0);
  const added = tree.workstreams.reduce(
    (n, w) => n + w.steps.filter((s) => s.inserted_by_revision > 0).length,
    0,
  );
  return { steps, added };
}
