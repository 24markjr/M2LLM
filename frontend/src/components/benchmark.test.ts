import { describe, expect, it } from "vitest";

import type { BenchmarkScore } from "../api/types";
import { scoreCell, systemLabel } from "./benchmark";

const row = (at: Partial<BenchmarkScore>): BenchmarkScore => ({
  scenario_id: "s",
  system: "plain",
  claims: 1,
  correct: null,
  supported: 0,
  sentences: 0,
  invented: [],
  citations: 0,
  citations_precise: 0,
  false_alarm: null,
  latency_ms: 0,
  error: "",
  answer: "",
  ...at,
});

describe("the benchmark view (Phase B1)", () => {
  it("names the systems", () => {
    expect(systemLabel("jarvis")).toBe("JARVIS");
    expect(systemLabel("plain")).toBe("Plain model");
    expect(systemLabel("openai:gpt-4o")).toBe("gpt-4o (frontier)");
  });

  it("summarises a cell from the counts, and marks a false alarm", () => {
    expect(scoreCell(row({ correct: 0.5, supported: 2, sentences: 3, invented: ["520,000"] })).text).toBe(
      "50% facts · 2/3 supported · 1 invented",
    );
    expect(scoreCell(row({ false_alarm: true }))).toEqual({ text: "false alarm", alarm: true });
    expect(scoreCell(row({ error: "HTTPError" })).text).toBe("failed: HTTPError");
  });
});
