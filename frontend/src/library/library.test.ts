import { describe, expect, it } from "vitest";

import type { Case, EvidenceItem } from "../api/types";
import { ALL, filterRows, folders, kindsOf, NO_FILTERS, sortRows, UNFILED, type LibraryRow } from "./library";

const row = (id: string, at: Partial<EvidenceItem> = {}, citations = 0): LibraryRow => ({
  item: {
    evidence_id: id,
    sha256: `ab${id}`.toLowerCase().padEnd(64, "0"),
    name: `${id}.txt`,
    kind: "text",
    parser: "text",
    bytes: 100,
    collected_at: "2026-10-01T00:00:00Z",
    collected_by: "analyst",
    source: "upload",
    classification: "UNCLASSIFIED",
    integrity: "VERIFIED",
    integrity_checked_at: null,
    case_id: null,
    ...at,
  },
  citations,
});

const ROWS = [
  row("EV-000001", { case_id: "CASE-1", kind: "pdf", bytes: 900 }, 2),
  row("EV-000002", { integrity: "FAILED", collected_at: "2026-10-05T00:00:00Z" }),
  row("EV-000003", { case_id: "CASE-9", classification: "CONFIDENTIAL", name: "Ledger Q3.xlsx", kind: "xlsx" }, 1),
];
const CASES = [
  { case_id: "CASE-1", title: "Aurora", status: "OPEN" },
  { case_id: "CASE-2", title: "Helix", status: "OPEN" },
  { case_id: "CASE-3", title: "Closed one", status: "CLOSED" },
] as Case[];

describe("the Library (Phase U8)", () => {
  it("files every item under a folder: all, unfiled, or its case", () => {
    expect(folders(ROWS, CASES)).toEqual([
      { id: ALL, label: "All files", count: 3 },
      { id: UNFILED, label: "Unfiled", count: 1 },
      { id: "CASE-1", label: "Aurora", count: 1 },
      // A case missing from the list keeps a folder, so its files stay reachable.
      { id: "CASE-9", label: "CASE-9", count: 1 },
      { id: "CASE-2", label: "Helix", count: 0 },
    ]);
  });

  it("filters by folder, text, kind, integrity, classification and citation", () => {
    const ids = (f: Partial<typeof NO_FILTERS>) => filterRows(ROWS, { ...NO_FILTERS, ...f }).map((r) => r.item.evidence_id);
    expect(ids({ folder: UNFILED })).toEqual(["EV-000002"]);
    expect(ids({ folder: "CASE-1" })).toEqual(["EV-000001"]);
    expect(ids({ query: "ledger" })).toEqual(["EV-000003"]);
    expect(ids({ query: "abev-000002" })).toEqual(["EV-000002"]);
    expect(ids({ kind: "pdf" })).toEqual(["EV-000001"]);
    expect(ids({ integrity: "FAILED" })).toEqual(["EV-000002"]);
    expect(ids({ classification: "CONFIDENTIAL" })).toEqual(["EV-000003"]);
    expect(ids({ citedOnly: true })).toEqual(["EV-000001", "EV-000003"]);
  });

  it("lists the kinds present and sorts by what the person chose", () => {
    expect(kindsOf(ROWS)).toEqual(["pdf", "text", "xlsx"]);
    expect(sortRows(ROWS, "collected")[0]?.item.evidence_id).toBe("EV-000002");
    expect(sortRows(ROWS, "size")[0]?.item.evidence_id).toBe("EV-000001");
    expect(sortRows(ROWS, "cited").map((r) => r.citations)).toEqual([2, 1, 0]);
    expect(sortRows(ROWS, "name")[0]?.item.name).toBe("EV-000001.txt");
  });
});
