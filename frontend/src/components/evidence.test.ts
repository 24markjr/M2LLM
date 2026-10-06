import { describe, expect, it } from "vitest";

import {
  custodyLabel,
  custodySummary,
  evidenceForCitation,
  evidenceIdFromHash,
  evidenceLink,
} from "./evidence";

describe("evidence", () => {
  it("links to an item only when the id is one", () => {
    expect(evidenceLink("EV-000012")).toBe("#/evidence/EV-000012");
    expect(evidenceLink("../etc")).toBe("#/evidence");
    expect(evidenceLink()).toBe("#/evidence");
  });

  it("reads an item id back from the hash", () => {
    expect(evidenceIdFromHash("#/evidence/EV-000012")).toBe("EV-000012");
    expect(evidenceIdFromHash("#/evidence")).toBe("");
    expect(evidenceIdFromHash("#/evidence/nope")).toBe("");
  });

  it("finds the exact version a mission read for a citation", () => {
    const map = { "report.txt": "EV-000003" };
    expect(evidenceForCitation(map, "report.txt")).toBe("EV-000003");
    expect(evidenceForCitation(map, "report.txt:r12")).toBe("EV-000003");
    expect(evidenceForCitation(map, "other.txt")).toBeUndefined();
    expect(evidenceForCitation(undefined, "report.txt")).toBeUndefined();
  });

  it("says what each custody step means, and its key detail", () => {
    expect(custodyLabel("CITED")).toBe("Cited by a finding");
    expect(custodyLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(custodySummary("CITED", { finding_id: "F-001", locator: "a.txt:r3", run_id: "run_1" })).toBe(
      "F-001 at a.txt:r3 (mission run_1)",
    );
    expect(
      custodySummary("METADATA_CHANGED", { classification: { from: "UNCLASSIFIED", to: "RESTRICTED" } }),
    ).toBe("classification: UNCLASSIFIED → RESTRICTED");
    expect(custodySummary("HASHED", { sha256: "abc" })).toBe("");
  });
});
