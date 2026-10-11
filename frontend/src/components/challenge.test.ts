import { describe, expect, it } from "vitest";

import type { ChallengeResult } from "../api/types";
import { challengeDelta } from "./challenge";

function result(before: number, after: number): ChallengeResult {
  return {
    finding_id: "F-001",
    claim: "x",
    outcome: after < before ? "OVERTURNED" : "WITHSTOOD",
    summary: "",
    counter_evidence: [],
    own_lines: "",
    negation_check: "",
    authority_note: "",
    confidence_before: before,
    confidence_after: after,
    after: { value: after, resolution_rate: 1, evidence_strength: 1, source_agreement: 1, classification_ceiling: 1 },
    challenged_by: "analyst",
    challenged_at: "",
  };
}

describe("challenge (Phase 48)", () => {
  it("shows what the challenge did to the number", () => {
    expect(challengeDelta(result(0.84, 0.1))).toBe("confidence 0.84 → 0.10 (−0.74)");
    expect(challengeDelta(result(0.9, 0.9))).toBe("confidence 0.90 → 0.90 (±0.00)");
  });
});
