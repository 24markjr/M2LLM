import { describe, expect, it } from "vitest";

import type { EventRecord, Finding, FinalReport, GapRecord, HypothesisSet } from "../api/types";
import { answerSentences, citationsOf, closingSections, journalSteps } from "./journal";

let n = 0;
const ev = (event_type: string, payload: Record<string, unknown> = {}): EventRecord => ({
  event_id: `e${n++}`,
  event_type,
  t_offset_ms: n,
  task_id: null,
  finding_id: null,
  payload,
});

function finding(id: string, status: string | null, claim = `claim ${id}`): Finding {
  return {
    finding_id: id,
    claim,
    classification: "FACT",
    confidence: { value: 0.8, resolution_rate: 1, evidence_strength: 1, source_agreement: 1, classification_ceiling: 1 },
    evidence: [
      {
        evidence_id: "E1",
        locator: { document_id: "ledger.txt", document_name: "ledger.txt", page: null, row: 12, char_start: null, char_end: null },
        resolution: "RESOLVED",
        resolution_note: "",
      },
    ],
    verification: status ? { status: status as never, issues: [], degraded: false, degraded_reason: "", verifier: "composite" } : null,
    derived_from_task_ids: [],
    revision: 0,
  } as unknown as Finding;
}

describe("the journal's steps (Phase U5)", () => {
  it("shows where a running investigation is, in plain words", () => {
    const events = [ev("RUN_STARTED"), ev("INTENT_CREATED", { goal: "investigate_contradictions" }), ev("PLAN_CREATED", { task_count: 4 }), ev("TASK_STARTED")];
    const steps = journalSteps(events, null, false);
    expect(steps.map((s) => s.state)).toEqual(["done", "done", "doing", "todo", "todo", "todo", "todo"]);
    expect(steps[0]?.detail).toBe("Goal: investigate contradictions");
    expect(steps[1]?.detail).toBe("4 step(s) planned");
  });

  it("counts verified findings and the gaps it went after", () => {
    const events = [
      ev("RUN_STARTED"),
      ev("INTENT_CREATED", { goal: "g" }),
      ev("PLAN_CREATED", { task_count: 2 }),
      ev("TASK_STARTED"),
      ev("FINDING_CREATED"),
      ev("FINDING_CREATED"),
      ev("FINDING_VERIFIED", { status: "SUPPORTED" }),
      ev("FINDING_REJECTED", { status: "UNSUPPORTED" }),
      ev("EVIDENCE_GAP_DETECTED", { missing: "the approved end date" }),
      ev("REPLAN_STARTED"),
      ev("SYNTHESIS_STARTED"),
      ev("SYNTHESIS_COMPLETED"),
    ];
    const steps = journalSteps(events, null, true);
    expect(steps.every((s) => s.state === "done")).toBe(true);
    expect(steps.find((s) => s.id === "verify")?.detail).toBe("1 of 2 verified");
    expect(steps.find((s) => s.id === "gaps")?.detail).toBe("1 gap(s), 0 closed, 1 new round(s) of work - latest: the approved end date");
  });

  it("marks steps a finished run never reached as skipped", () => {
    const steps = journalSteps([ev("RUN_STARTED"), ev("RUN_FAILED")], null, true);
    expect(steps.slice(1).every((s) => s.state === "skipped")).toBe(true);
  });
});

describe("the answer (Phase U5)", () => {
  const report = (checks: boolean): FinalReport =>
    ({
      sections: [{ heading: "Executive Summary", kind: "EXECUTIVE_SUMMARY", narrative: "Spend exceeded approval.", items: [], finding_ids: [] }],
      limitations: [{ description: "The board minutes were not provided.", cause: "" }],
      narrative_checks: checks
        ? [{ section: "Executive Summary", overall: "", sentences: [{ sentence: "Spend exceeded approval.", status: "SUPPORTED", reasoning: "r12", ungrounded: [] }] }]
        : [],
    }) as unknown as FinalReport;

  it("marks each sentence of the summary with its checked status", () => {
    expect(answerSentences(report(true))).toEqual([{ text: "Spend exceeded approval.", status: "verified", reasoning: "r12" }]);
  });

  it("says when a summary was not checked sentence by sentence", () => {
    const [only] = answerSentences(report(false));
    expect(only?.status).toBe("unknown");
    expect(only?.reasoning).toMatch(/not checked/);
  });

  it("links a citation to its evidence item, with where in the file", () => {
    const [c] = citationsOf(finding("F-1", "SUPPORTED"), { "ledger.txt": "EV-000012" });
    expect(c).toMatchObject({ label: "ledger.txt · line 12", href: "#/evidence/EV-000012", resolved: true });
    expect(citationsOf(finding("F-1", "SUPPORTED"), {})[0]?.href).toBe("");
  });

  it("ends with what could not be established, what would change it, and what to get next", () => {
    const gaps: GapRecord[] = [{ gap_id: "G1", gap_type: "MISSING", description: "No approved baseline date.", resolved: false, finding_id: "" }];
    const hypotheses = {
      hypotheses: [
        {
          statement: "The vendor delayed delivery",
          status: "OPEN",
          decisive_evidence: "the vendor's dispatch record",
          next_evidence: { kind: "ANALYST_REQUEST", text: "Ask the vendor for the dispatch record.", query: "", leads: [] },
        },
      ],
    } as unknown as HypothesisSet;
    const closing = closingSections(
      [finding("F-1", "UNSUPPORTED", "The vendor was paid twice."), finding("F-2", "PARTIALLY_SUPPORTED", "The overrun began in Q3.")],
      gaps,
      hypotheses,
      report(true),
    );
    expect(closing.couldNot).toEqual([
      "No approved baseline date.",
      "Not established: The vendor was paid twice.",
      "The board minutes were not provided.",
    ]);
    expect(closing.wouldChange[0]).toBe("The vendor delayed delivery - the vendor's dispatch record");
    expect(closing.wouldChange[1]).toMatch(/The overrun began in Q3/);
    expect(closing.next).toEqual(["Ask the vendor for the dispatch record."]);
  });
});
