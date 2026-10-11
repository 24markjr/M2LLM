import { describe, expect, it } from "vitest";

import type { Hypothesis } from "../api/types";
import { draftFromHash } from "./workspaces";
import { documentOf, hypothesesHeadline, supportText, testLink } from "./hypotheses";

const open: Hypothesis = {
  hypothesis_id: "H-2",
  statement: "The power dip on rack B caused the outage.",
  supporting: [],
  contradicting: [],
  support: 0.9,
  against: 0.2,
  status: "OPEN",
  status_reason: "",
  decisive_evidence: "the UPS log for rack B",
  next_evidence: {
    kind: "SEARCH",
    text: "Read these lines next",
    query: "UPS log rack B",
    leads: [
      { locator: "lyra_facilities_note.txt:r5", text: "The UPS log for rack B is held by the vendor" },
      { locator: "2. Detailed Timeline.pdf:p3", text: "rack B" },
    ],
  },
};

describe("hypotheses (Phase 47)", () => {
  it("reads the document out of a locator, spaces included", () => {
    expect(documentOf("lyra_facilities_note.txt:r5")).toBe("lyra_facilities_note.txt");
    expect(documentOf("2. Detailed Timeline.pdf:p3")).toBe("2. Detailed Timeline.pdf");
  });

  it("opens an investigation of an open explanation on its leads, in its case", () => {
    const draft = draftFromHash(testLink(open, "CASE-2026-00010"));
    expect(draft.documents).toEqual(["lyra_facilities_note.txt", "2. Detailed Timeline.pdf"]);
    expect(draft.caseId).toBe("CASE-2026-00010");
    expect(draft.objective).toContain("The power dip on rack B caused the outage.");
    expect(draft.objective).toContain("Look for: the UPS log for rack B.");
  });

  it("shows support as computed: net, for and against", () => {
    expect(supportText(open)).toBe("+0.70 (0.90 for, 0.20 against)");
  });

  it("says why there are none", () => {
    expect(
      hypothesesHeadline({
        question: "",
        hypotheses: [],
        determined: false,
        summary: "",
        skipped_reason: "1 explanation(s) proposed; competing explanations need 2",
        llm_calls: 1,
      }),
    ).toBe("Not run: 1 explanation(s) proposed; competing explanations need 2");
  });
});
