import { describe, expect, it } from "vitest";

import type { AnswerSide, Comparison, Receipt } from "../api/types";
import { differences, receiptText, shortHash, supportedShare, tallyLine } from "./proof";

const tally = (supported: number, sentences: number, unsupported = 0) => ({
  sentences,
  supported,
  partial: 0,
  unsupported,
  contradicted: 0,
  insufficient: 0,
});

const side = (label: string, t: ReturnType<typeof tally>, ungrounded: string[], cited = 0): AnswerSide => ({
  label,
  answer: "x",
  check: null,
  tally: t,
  ungrounded,
  cited_findings: cited,
  latency_ms: 0,
});

describe("proof in words (Phase U7)", () => {
  it("counts sentences without grading them", () => {
    expect(tallyLine(tally(3, 4, 1))).toBe("3 of 4 sentence(s) supported by a line in the files; 1 unsupported");
    expect(tallyLine(tally(0, 0))).toBe("No answer to check.");
    expect(supportedShare(tally(0, 0))).toBeNull();
  });

  it("states the differences from the counts the server made", () => {
    const c = {
      plain: side("Plain model", tally(1, 2, 1), ["520,000"]),
      jarvis: side("JARVIS", tally(2, 2), [], 2),
      truncated: true,
    } as unknown as Comparison;
    const lines = differences(c);
    expect(lines[0]).toBe("Plain model: 50% of sentences supported. JARVIS: 100% of sentences supported.");
    expect(lines[1]).toContain("plain model 1 date or figure, JARVIS 0 dates or figures");
    expect(lines[2]).toContain("JARVIS 2");
    expect(lines.at(-1)).toContain("first part");
  });

  it("prints a receipt carrying every file hash and the receipt hash", () => {
    const r = {
      run_id: "run_1",
      question: "Q?",
      model: "qwen3:4b",
      prompt_versions: { reasoning: 3 },
      started_at: null,
      finished_at: null,
      documents: [{ name: "a.txt", sha256: "f".repeat(64), characters: 10, evidence_id: "" }],
      findings: [
        { finding_id: "F-001", claim: "c", classification: "FACT", verification: "SUPPORTED", verifier: "baseline", degraded: false, confidence: 0.9, citations: 2, citations_resolved: 1 },
      ],
      answer: tally(1, 1),
      tasks_planned: 3,
      tasks_completed: 3,
      gaps_open: 0,
      receipt_hash: "a".repeat(64),
    } as Receipt;
    const text = receiptText(r);
    expect(text).toContain(`${"f".repeat(64)}  a.txt`);
    expect(text).toContain("F-001  SUPPORTED  1/2 citation(s) resolved  90%");
    expect(text).toContain("a".repeat(64));
    expect(shortHash("a".repeat(64))).toBe("aaaaaaaa…aaaaaaaa");
  });
});
