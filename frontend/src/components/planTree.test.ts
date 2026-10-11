import { describe, expect, it } from "vitest";

import type { PlanTree } from "../api/types";
import { changeHeadline, planCounts } from "./planTree";

const step = (task_id: string, inserted = 0) => ({
  task_id,
  label: "Found more evidence",
  task_type: "retrieve_evidence",
  why: "inserted by the replanning loop to close gap G-001: the approved baseline",
  inputs: [],
  action: "document_search",
  output: "",
  depends_on: [],
  status: "COMPLETED" as const,
  inserted_by_revision: inserted,
});

const tree: PlanTree = {
  run_id: "run_0123456789ab",
  objective: "Compare the reports.",
  workstreams: [
    { name: "Extract what the documents state", steps: [step("task_001"), step("task_002")] },
    { name: "Close evidence gaps", steps: [step("task_004", 1)] },
  ],
  changes: [
    {
      revision: 1,
      trigger: "EVIDENCE_GAP",
      reason: "1 task(s) added to close detected evidence gaps",
      triggered_by: "G-001",
      added: [step("task_004", 1)],
      skipped: [],
      tasks_before: 3,
      tasks_after: 4,
    },
  ],
  repairs: [],
};

describe("plan tree (Phase 49)", () => {
  it("counts the steps and the ones added during the run", () => {
    expect(planCounts(tree)).toEqual({ steps: 3, added: 1 });
  });

  it("says how and why the plan changed", () => {
    expect(changeHeadline(tree.changes[0]!)).toBe(
      "Revision 1 (evidence gap G-001): added 1 step(s) - 3 → 4 steps. 1 task(s) added to close detected evidence gaps",
    );
  });
});
