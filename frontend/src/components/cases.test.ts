import { describe, expect, it } from "vitest";

import type { Finding, TaskNode } from "../api/types";
import { caseIdFromHash, caseLink, conclusion, stepsFrom } from "./cases";
import { draftFromHash, newMissionLink } from "./workspaces";

const node = (over: Partial<TaskNode>): TaskNode => ({
  task_id: "task_001",
  task_type: "compare_sources",
  description: "",
  status: "PENDING",
  depends_on: [],
  tool_id: "",
  inserted_by_replan: false,
  label: "Cross-check the sources against each other",
  ...over,
});

describe("cases", () => {
  it("links to a case only when the id is one", () => {
    expect(caseLink("CASE-2026-00001")).toBe("#/case/CASE-2026-00001");
    expect(caseLink("nope")).toBe("#/cases"); // the case list since U4
    expect(caseIdFromHash("#/case/CASE-2026-00001")).toBe("CASE-2026-00001");
    expect(caseIdFromHash("#/case/x")).toBe("");
  });

  it("carries a case through a New Investigation link", () => {
    const link = newMissionLink({ caseId: "CASE-2026-00007", documents: ["a.txt"] });
    expect(draftFromHash(link)).toEqual({ caseId: "CASE-2026-00007", documents: ["a.txt"] });
    expect(draftFromHash("#/new?case=..%2Fx")).toEqual({});
  });

  it("turns tasks into steps in plain words", () => {
    const steps = stepsFrom([
      node({ status: "COMPLETED", label: "Cross-checked the sources against each other" }),
      node({ task_id: "task_002", status: "RUNNING", label: "Looking for contradictions" }),
      node({ task_id: "task_003", inserted_by_replan: true, label: "", description: "find the baseline" }),
    ]);
    expect(steps.map((s) => s.state)).toEqual(["done", "doing", "todo"]);
    expect(steps[2]).toMatchObject({ label: "find the baseline", added: true });
  });

  it("concludes only what passed verification, and says so when nothing did", () => {
    const finding = (status: string, claim: string) =>
      ({ claim, verification: { status } }) as unknown as Finding;
    expect(conclusion([finding("SUPPORTED", "A"), finding("UNSUPPORTED", "B")], true)).toEqual(["A"]);
    expect(conclusion([], false)).toEqual([]);
    expect(conclusion([], true)[0]).toMatch(/correct answer/);
    expect(conclusion([finding("UNSUPPORTED", "B")], true)[0]).toMatch(/Nothing passed/);
  });
});
