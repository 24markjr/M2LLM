import { describe, expect, it } from "vitest";

import type { EventRecord, Finding } from "../api/types";
import { clock, progressLine, progressOf } from "../components/progress";
import { proofTally } from "./proof";

const finding = (status: string): Finding => ({ verification: status ? { status } : null }) as unknown as Finding;
const event = (event_type: string): EventRecord => ({
  event_id: event_type,
  event_type,
  t_offset_ms: 0,
  task_id: null,
  finding_id: null,
  payload: {},
});

describe("demo readiness: the proof card and the progress line", () => {
  it("counts each verdict, the files fingerprinted and the time taken", () => {
    const tally = proofTally(
      [finding("SUPPORTED"), finding("CONTRADICTED"), finding("PARTIALLY_SUPPORTED"), finding("")],
      { "a.pdf": "EV-1", "b.docx": "EV-2", "c_hi.txt": "EV-3" },
      ["c_hi.txt"],
      "2026-10-30T10:00:00Z",
      "2026-10-30T10:03:18Z",
    );
    expect(tally).toEqual({ claims: 4, verified: 1, partly: 1, caught: 1, unproven: 1, files: 3, translated: 1, seconds: 198 });
  });

  it("says what a running investigation is doing, from its own events", () => {
    const progress = progressOf(
      ["RUN_STARTED", "PLAN_CREATED", "LLM_CALL_COMPLETED", "TASK_COMPLETED", "LLM_CALL_COMPLETED", "FINDING_VERIFIED"].map(event),
      4,
    );
    expect(progress.doing).toContain("Checking each finding");
    expect(progressLine(progress, 75)).toBe(
      "Checking each finding against the lines it cites · 1:15 elapsed · 2 model step(s) · 1 of 4 tasks · 1 verified, 0 rejected",
    );
    expect(progressOf([event("BUDGET_WARNING")], 0).doing).toContain("Time limit reached");
    expect(clock(5)).toBe("0:05");
  });
});
