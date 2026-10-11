import { describe, expect, it } from "vitest";

import type { EvidenceRef, Finding } from "../api/types";
import { authorityWords, custodySummary } from "./evidence";
import { authorityText, singleSource, statementHelp, statementLabel, statementType } from "./statements";

function ref(document: string, row: number, resolved = true): EvidenceRef {
  return {
    evidence_id: `E-${row}`,
    locator: { document_id: document, document_name: document, page: null, row, char_start: null, char_end: null },
    resolution: resolved ? "RESOLVED" : "UNRESOLVED",
    resolution_note: "",
  } as EvidenceRef;
}

function finding(refs: EvidenceRef[], extra: Partial<Finding> = {}): Finding {
  return {
    finding_id: "F-001",
    claim: "x",
    classification: "FACT",
    confidence: { value: 0.85 } as Finding["confidence"],
    evidence: refs,
    verification: null,
    derived_from_task_ids: [],
    revision: 0,
    ...extra,
  };
}

describe("statement types (Phase 45)", () => {
  it("shows the engine's type when it has one", () => {
    expect(statementType(finding([ref("a", 1), ref("b", 2)], { statement_type: "CONTRADICTION" }))).toBe(
      "CONTRADICTION",
    );
  });

  it("never shows one document as a fact, even for a finding stored before Phase 45", () => {
    const old = finding([ref("sow.docx", 50)]);
    expect(singleSource(old)).toBe(true);
    expect(statementType(old)).toBe("SOURCE_CLAIM");
    expect(statementType(finding([ref("a", 1), ref("b", 2)]))).toBe("FACT");
    expect(statementType(finding([ref("a", 1), ref("b", 2, false)]))).toBe("HYPOTHESIS");
    expect(statementType(finding([ref("a", 1, false)]))).toBe("UNKNOWN");
  });

  it("labels a proposed kind with what it rests on", () => {
    const risk = finding([ref("sow.docx", 9)], { statement_type: "RISK", statement_basis: "SOURCE_CLAIM" });
    expect(statementLabel(risk)).toBe("RISK on SOURCE CLAIM");
    expect(statementLabel(finding([ref("a", 1)], { statement_type: "SOURCE_CLAIM", statement_basis: "SOURCE_CLAIM" }))).toBe(
      "SOURCE CLAIM",
    );
  });

  it("says what the model proposed in the help text", () => {
    const f = finding([ref("a", 1)], { statement_type: "SOURCE_CLAIM", proposed_type: "FACT" });
    expect(statementHelp(f)).toContain("The model proposed: FACT");
  });
});

describe("source authority (Phase 45)", () => {
  it("puts a tier in words, and an unassessed one as such", () => {
    expect(authorityWords("CORRESPONDENCE")).toBe("correspondence");
    expect(authorityWords("UNASSESSED")).toBe("not assessed");
    expect(authorityWords(undefined)).toBe("not assessed");
    expect(authorityText("APPROVED")).toBe("authority: approved");
  });

  it("summarises an authority change with its reason", () => {
    expect(
      custodySummary("METADATA_CHANGED", { authority: { from: "DRAFT", to: "APPROVED" }, reason: "signed copy" }),
    ).toBe("authority: DRAFT → APPROVED; reason: signed copy");
  });
});
