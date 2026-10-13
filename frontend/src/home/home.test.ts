import { describe, expect, it } from "vitest";

import { attentionItems, type MissionLike } from "./attention";
import { caseTitleFor, MODES, objectiveFor, questionProblem } from "./modes";
import { packById, PACKS } from "./packs";

describe("composer modes (Phase U4)", () => {
  it("frames the question for the engine, and leaves Investigate as asked", () => {
    expect(objectiveFor("investigate", "  Was shipment 4821 late? ")).toBe("Was shipment 4821 late?");
    expect(objectiveFor("compare", "on dates")).toMatch(/^Compare the attached documents.*on dates$/);
    expect(objectiveFor("security", "lateral movement")).toMatch(/^Examine the attached security logs/);
    expect(objectiveFor("timeline", "")).toBe("");
    expect(MODES.map((m) => m.id)).toEqual(["investigate", "compare", "timeline", "security"]);
  });

  it("names a new case from the first sentence of the question", () => {
    expect(caseTitleFor("Was shipment 4821 late? Check every statement.")).toBe("Was shipment 4821 late?");
    expect(caseTitleFor("x".repeat(120))).toHaveLength(80);
    expect(caseTitleFor("ab")).toBe("Untitled investigation");
  });

  it("says what is wrong with a question the engine would refuse", () => {
    expect(questionProblem("")).toBe("Ask a question first.");
    expect(questionProblem("why?")).toMatch(/at least 8/);
    expect(questionProblem("Was shipment 4821 late?")).toBe("");
    expect(questionProblem("x".repeat(1990), "compare")).toMatch(/at most 2,000/);
  });
});

describe("domain packs (Phase U4)", () => {
  it("has the six packs, each with starters, and falls back to General", () => {
    expect(PACKS.map((p) => p.id)).toEqual(["general", "investigation", "finance", "legal", "healthcare", "cyber"]);
    expect(PACKS.every((p) => p.starters.length >= 2)).toBe(true);
    expect(packById("nope").id).toBe("general");
    expect(packById("healthcare").notice).toMatch(/not a diagnosis/);
  });

  it("starts security questions in the Security logs mode", () => {
    expect(packById("cyber").starters.every((s) => s.mode === "security")).toBe(true);
  });
});

describe("needs your attention (Phase U4)", () => {
  const now = new Date("2026-10-13T12:00:00Z");
  const m = (over: Partial<MissionLike>): MissionLike => ({
    run_id: "run_x",
    objective: "q",
    status: "COMPLETED",
    created_at: "2026-10-13T10:00:00Z",
    finished_at: "2026-10-13T10:05:00Z",
    finding_count: 0,
    verified_count: 0,
    unresolved_gap_count: 0,
    ...over,
  });

  it("lists running work first, then unverified findings, then open questions", () => {
    const items = attentionItems(
      [
        m({ run_id: "run_a", finding_count: 3, verified_count: 1 }),
        m({ run_id: "run_b", status: "RUNNING" }),
        m({ run_id: "run_c", unresolved_gap_count: 2 }),
        m({ run_id: "run_d", finding_count: 2, verified_count: 2 }),
      ],
      now,
    );
    expect(items.map((i) => i.kind)).toEqual(["running", "review", "open"]);
    expect(items[1]?.detail).toBe("2 of 3 finding(s) not verified - worth a look");
    expect(items[0]?.href).toBe("#/mission/run_b");
  });

  it("leaves out old work and caps the list", () => {
    const old = m({ finding_count: 2, finished_at: "2026-09-01T00:00:00Z" });
    expect(attentionItems([old], now)).toEqual([]);
    const many = Array.from({ length: 10 }, (_, i) => m({ run_id: `run_${i}`, status: "RUNNING" }));
    expect(attentionItems(many, now)).toHaveLength(6);
  });
});
