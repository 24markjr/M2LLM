import { describe, expect, it } from "vitest";

import type { QualitySummary } from "../api/types";
import { figure, qualitySum, trendChart, trendSegments } from "./quality";

const summary: QualitySummary = {
  formula: "quality = mean(...)",
  value: 0.9,
  components: [
    { name: "grounding", value: 1, formula: "1 - unsupported_claim_rate", source: "r.json", dataset: "20 scenarios" },
    { name: "challenge", value: 0.8, formula: "catch x (1 - false alarm)", source: "c.json", dataset: "12 findings" },
  ],
  categories: [],
  agent_formula: "agent quality = mean(...)",
  trend: [
    { generated_at: "1", report: "a", agent_quality: 0.88, comparable_key: "k1" },
    { generated_at: "2", report: "b", agent_quality: 0.94, comparable_key: "k1" },
    { generated_at: "3", report: "c", agent_quality: 0.9, comparable_key: "k2" },
  ],
  missing: [],
};

describe("quality (Phase 54)", () => {
  it("lays out the mean it reports", () => {
    expect(qualitySum(summary)).toBe("mean(1.000, 0.800) = 0.900");
    expect(qualitySum({ ...summary, value: null })).toBe("");
  });

  it("never joins the trend across a change of configuration", () => {
    expect(trendSegments(summary)).toEqual([
      { key: "k1", values: [0.88, 0.94] },
      { key: "k2", values: [0.9] },
    ]);
  });

  it("shows an absent figure as a dash, not a zero", () => {
    expect(figure(null)).toBe("-");
    expect(figure(0)).toBe("0.000");
  });
});

describe("the quality trend chart (U9)", () => {
  const pad = { top: 0, right: 0, bottom: 0, left: 0 };

  it("joins points only within one configuration, and breaks between them", () => {
    const { segments, breaks } = trendChart(summary, 200, 100, pad);
    expect(segments.map((s) => s.map((p) => p.report))).toEqual([["a", "b"], ["c"]]);
    expect(breaks).toEqual([150]);
  });

  it("places 0 at the bottom and 1 at the top, spread across the width", () => {
    const { segments } = trendChart(summary, 200, 100, pad);
    const [first, second] = segments[0]!;
    expect(first).toMatchObject({ x: 0, y: 12 });
    expect(second!.x).toBe(100);
    expect(second!.y).toBeCloseTo(6);
  });
});
