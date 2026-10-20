import { describe, expect, it } from "vitest";

import type { Finding, HypothesisSet, SourceLocator } from "../api/types";
import { initialLayout, lineOf, marksIn, pinsAndStrings, rangeOf, segments } from "./board";

const loc = (document: string, at: Partial<SourceLocator>): SourceLocator => ({
  document_id: document,
  document_name: document,
  page: null,
  row: null,
  char_start: null,
  char_end: null,
  ...at,
});

function finding(id: string, locators: SourceLocator[], statement_type = "FACT"): Finding {
  return {
    finding_id: id,
    claim: `claim ${id}`,
    classification: "FACT",
    statement_type,
    confidence: { value: 0.8, resolution_rate: 1, evidence_strength: 1, source_agreement: 1, classification_ceiling: 1 },
    evidence: locators.map((locator, i) => ({ evidence_id: `E${i}`, locator, resolution: "RESOLVED", resolution_note: "" })),
    verification: null,
    derived_from_task_ids: [],
    revision: 0,
  } as unknown as Finding;
}

const TEXT = "budget 380000\napproved 310000\nstart March";
const SOURCES = { "report.txt": TEXT, "ledger.csv": "a,b\n1,2" };

describe("placing a citation in the text (Phase U6)", () => {
  it("uses the character range when the citation has one", () => {
    expect(rangeOf(loc("report.txt", { char_start: 7, char_end: 13 }), TEXT)).toEqual({ start: 7, end: 13 });
  });

  it("marks the whole line for a row", () => {
    const r = rangeOf(loc("report.txt", { row: 2 }), TEXT);
    expect(r && TEXT.slice(r.start, r.end)).toBe("approved 310000");
  });

  it("does not invent a place it cannot find", () => {
    expect(rangeOf(loc("report.txt", { row: 9 }), TEXT)).toBeNull();
    expect(rangeOf(loc("report.txt", { page: 2 }), TEXT)).toBeNull();
    expect(rangeOf(loc("report.txt", { char_start: 500, char_end: 600 }), TEXT)).toBeNull();
  });

  it("counts lines from one", () => {
    expect(lineOf(TEXT, 0)).toBe(1);
    expect(lineOf(TEXT, TEXT.indexOf("start"))).toBe(3);
  });

  it("splits the text so every cited span knows its findings, and nothing is lost", () => {
    const marks = marksIn(
      "report.txt",
      [finding("F-1", [loc("report.txt", { row: 1 })]), finding("F-2", [loc("report.txt", { char_start: 7, char_end: 13 })])],
      SOURCES,
    );
    const pieces = segments(TEXT, marks);
    expect(pieces.map((p) => p.text).join("")).toBe(TEXT);
    expect(pieces.find((p) => p.text === "380000")?.findings).toEqual(["F-1", "F-2"]);
    expect(pieces.find((p) => p.text === "budget ")?.findings).toEqual(["F-1"]);
    expect(pieces.at(-1)?.findings).toEqual([]);
  });
});

describe("the pin board (Phase U6)", () => {
  it("strings two findings that cite the same line, and each to its file", () => {
    const { pins, strings } = pinsAndStrings(
      [finding("F-1", [loc("report.txt", { row: 1 })]), finding("F-2", [loc("report.txt", { char_start: 0, char_end: 6 })])],
      SOURCES,
    );
    expect(pins.map((p) => p.id)).toEqual(["F-1", "F-2", "doc:report.txt"]);
    expect(strings.find((s) => s.kind === "same-line")).toMatchObject({ from: "F-1", to: "F-2" });
    expect(strings.filter((s) => s.kind === "cites")).toHaveLength(2);
  });

  it("draws nothing between findings the run does not connect", () => {
    const { strings } = pinsAndStrings(
      [finding("F-1", [loc("report.txt", { row: 1 })]), finding("F-2", [loc("ledger.csv", { row: 2 })])],
      SOURCES,
    );
    expect(strings.every((s) => s.kind === "cites")).toBe(true);
  });

  it("marks a contradiction over a shared file, and keeps only the strongest string per pair", () => {
    const { strings } = pinsAndStrings(
      [
        finding("F-1", [loc("report.txt", { row: 1 })], "CONTRADICTION"),
        finding("F-2", [loc("report.txt", { row: 3 })]),
        finding("F-3", [loc("report.txt", { row: 1 })]),
      ],
      SOURCES,
    );
    expect(strings.find((s) => s.from === "F-1" && s.to === "F-2")?.kind).toBe("contradiction");
    // F-1 and F-3 are both a contradiction and the same line: the same line wins.
    expect(strings.filter((s) => [s.from, s.to].sort().join() === "F-1,F-3").map((s) => s.kind)).toEqual(["same-line"]);
  });

  it("strings findings that bear on the same explanation", () => {
    const hypotheses = {
      hypotheses: [{ statement: "the budget was overrun", supporting: [{ finding_id: "F-1" }], contradicting: [{ finding_id: "F-2" }] }],
    } as unknown as HypothesisSet;
    const { strings } = pinsAndStrings(
      [finding("F-1", [loc("report.txt", { row: 1 })]), finding("F-2", [loc("ledger.csv", { row: 2 })])],
      SOURCES,
      hypotheses,
    );
    expect(strings.find((s) => s.kind === "same-explanation")?.why).toBe("the budget was overrun");
  });

  it("lays files above findings, without overlap", () => {
    const { pins } = pinsAndStrings(
      [finding("F-1", [loc("report.txt", { row: 1 })]), finding("F-2", [loc("ledger.csv", { row: 2 })])],
      SOURCES,
    );
    const at = initialLayout(pins, 400);
    const keys = new Set(Object.values(at).map((p) => `${p.x},${p.y}`));
    expect(keys.size).toBe(pins.length);
    expect(at["doc:report.txt"]!.y).toBeLessThan(at["F-1"]!.y);
  });
});
