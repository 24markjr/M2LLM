import { describe, expect, it } from "vitest";

import type { FindingReview } from "../api/types";
import { auditLine, reviewBadge, reviewSummary } from "./review";

const pending: FindingReview = {
  run_id: "run_0123456789ab",
  finding_id: "F-001",
  claim: "x",
  statement_type: "CONTRADICTION",
  required: true,
  required_because: ["it reports a contradiction"],
  state: "PENDING",
  history: [],
};

describe("review (Phase 50)", () => {
  it("badges a finding that needs review, and not one that does not", () => {
    expect(reviewBadge(pending)).toBe("REVIEW: PENDING");
    expect(reviewBadge({ ...pending, required: false })).toBe("");
    expect(reviewBadge(undefined)).toBe("");
  });

  it("says why, and who decided last", () => {
    const rejected: FindingReview = {
      ...pending,
      state: "REJECTED",
      history: [
        {
          decision_id: 1,
          run_id: pending.run_id,
          finding_id: "F-001",
          state: "REJECTED",
          reviewer: "reviewer-3",
          reason: "superseded",
          modified_claim: "",
          at: "",
        },
      ],
    };
    expect(reviewSummary(rejected)).toBe("needs review: it reports a contradiction · rejected by reviewer-3: superseded");
  });

  it("writes an audit line with its outcome", () => {
    expect(
      auditLine({
        entry_id: 1,
        at: "",
        actor: "analyst-7",
        action: "POST /api/v1/missions",
        target: "missions",
        status_code: 202,
        details: {},
      }),
    ).toBe("POST /api/v1/missions → 202, by analyst-7");
  });
});
