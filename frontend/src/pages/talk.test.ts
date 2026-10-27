import { describe, expect, it } from "vitest";

import type { ToolStep, Turn } from "../api/types";
import { pendingQuestion, stopLabel, toolSummary } from "./talk";

const step = (tool: string): ToolStep => ({ tool, arguments: {}, result: "" });

describe("the investigation conversation (v4 Phase 3)", () => {
  it("says why an answer stopped, and nothing when it simply answered", () => {
    expect(stopLabel("ANSWERED")).toBe("");
    expect(stopLabel("STEP_LIMIT")).toContain("five lookups");
    expect(stopLabel("ASKED_USER")).toBe("needs your answer");
  });

  it("summarises the tools an answer rests on", () => {
    expect(toolSummary([step("search_evidence"), step("search_evidence"), step("read_span"), step("calculate")])).toBe(
      "searched 2×, read 1 passage, calculated",
    );
    expect(toolSummary([])).toBe("");
  });

  it("knows when the assistant is waiting on the person", () => {
    const asked = { role: "assistant", stop_reason: "ASKED_USER", question: "Which contract?" } as Turn;
    expect(pendingQuestion([asked])).toBe("Which contract?");
    expect(pendingQuestion([{ ...asked, stop_reason: "ANSWERED" }])).toBe("");
    expect(pendingQuestion([])).toBe("");
  });
});
