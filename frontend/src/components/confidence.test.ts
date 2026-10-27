import { describe, expect, it } from "vitest";

import type { Confidence } from "../api/types";
import { confidenceSum, costs, evidenceLabel, factorRows, SCORE_NOTE } from "./confidence";

const decomposed: Confidence = {
  value: 0.89,
  resolution_rate: 1,
  evidence_strength: 1,
  source_agreement: 0.6,
  classification_ceiling: 1,
  weighted: 0.89,
  penalty: 0,
  factors: [
    { name: "resolution", value: 1, weight: 0, contribution: 0, reason: "1 of 1 resolved", assessed: true },
    { name: "evidence_strength", value: 1, weight: 0.2, contribution: 0.2, reason: "1 line", assessed: true },
    { name: "independence", value: 0.6, weight: 0.25, contribution: 0.15, reason: "1 document", assessed: true },
    { name: "authority", value: 0.9, weight: 0.1, contribution: 0.09, reason: "official", assessed: true },
    { name: "verification", value: 1, weight: 0.35, contribution: 0.35, reason: "supported", assessed: true },
    { name: "temporal_consistency", value: 1, weight: 0.1, contribution: 0.1, reason: "no date", assessed: true },
  ],
};

describe("confidence (Phase 46)", () => {
  it("lays the sum out so it adds up", () => {
    expect(confidenceSum(decomposed)).toBe("0.89 = resolution 1.00 × weighted 0.89");
    const total = factorRows(decomposed)
      .filter((r) => r.weight !== "gate")
      .reduce((sum, r) => sum + Number(r.contribution.replace("−", "-")), 0);
    expect(total).toBeCloseTo(0.89, 2);
  });

  it("names the gate, the weights and the penalty", () => {
    const rows = factorRows({
      ...decomposed,
      penalty: 0.15,
      factors: [
        ...decomposed.factors!,
        { name: "disputed", value: 0.15, weight: 0, contribution: -0.15, reason: "F-001", assessed: true },
      ],
    });
    expect(rows[0]?.weight).toBe("gate");
    expect(rows[2]).toMatchObject({ name: "independence", weight: "0.25", contribution: "+0.15" });
    expect(rows[rows.length - 1]).toMatchObject({ weight: "penalty", contribution: "−0.15" });
  });

  it("shows the cap when it applied", () => {
    expect(confidenceSum({ ...decomposed, value: 0.85, weighted: 0.94, classification_ceiling: 0.85 })).toBe(
      "0.85 = resolution 1.00 × weighted 0.94 = 0.94, capped at 0.85",
    );
  });

  it("says what held it down, largest first", () => {
    expect(costs(decomposed).map((c) => c.name)).toEqual(["independence", "authority"]);
    expect(costs(decomposed)[0]?.cost).toBeCloseTo(0.1, 3);
  });

  it("has nothing to lay out for a confidence from before Phase 46", () => {
    const old: Confidence = { value: 0.85, resolution_rate: 1, evidence_strength: 1, source_agreement: 0.85, classification_ceiling: 1 };
    expect(factorRows(old)).toEqual([]);
    expect(confidenceSum(old)).toBe("");
  });
});

describe("evidence labels (v4 Phase 2)", () => {
  it("names the score in words, and says it is not a probability", () => {
    expect([0, 0.2, 0.4, 0.69, 0.7, 1].map(evidenceLabel)).toEqual([
      "no evidence",
      "weak evidence",
      "moderate evidence",
      "moderate evidence",
      "strong evidence",
      "strong evidence",
    ]);
    expect(SCORE_NOTE).toContain("not a probability");
  });
});
