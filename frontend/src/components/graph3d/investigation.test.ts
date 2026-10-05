/**
 * Phase 36: the links between Member 3's views, tested without a browser.
 *
 * The owner's rule for this phase is that everything is interrelated, so what is tested here is
 * mostly where a click leads: a contradiction to all of its sides, a claim to its entity, a name to
 * its investigation, an entity to its memory and back to the graph.
 */

import { describe, expect, it } from "vitest";

import type { ClaimConflict, KnowledgeGraphView, KnowledgeSnapshot } from "../../api/types";
import {
  conflictSpotlight,
  documentNodeId,
  entityOfSelection,
  findEntity,
  forEntity,
  formatDate,
  graphLink,
  hashQuery,
  localInvestigation,
  memoryLink,
  neighbourName,
  orderLabel,
  relationLabel,
  togglePick,
} from "./investigation";

const CONFLICT: ClaimConflict = {
  conflict_id: "CON-001",
  entity_id: "ENT-001",
  entity_name: "Shipment 4821",
  attribute: "arrival_date",
  kind: "DATE",
  sides: [
    { value: "14 September", claim_ids: ["CLM-001"], sources: ["shipment_report_a.txt:r1"] },
    { value: "16 September", claim_ids: ["CLM-002"], sources: ["shipment_report_b.txt:r1"] },
  ],
};

function claim(id: string, entity: string, attribute: string, value: string, source: string) {
  return {
    claim_id: id,
    entity_id: entity,
    attribute,
    value,
    source,
    document_id: source.split(":")[0] ?? source,
    line: 1,
    quote: "",
    grounded: true,
  };
}

const SNAPSHOT: KnowledgeSnapshot = {
  entities: [
    { entity_id: "ENT-001", name: "Shipment 4821", entity_type: "SHIPMENT", aliases: ["Shipment #4821"], sources: ["shipment_report_a.txt:r1"] },
    { entity_id: "ENT-002", name: "Rahul Sharma", entity_type: "PERSON", aliases: [], sources: ["shipment_employee_statement.txt:r1"] },
    { entity_id: "ENT-003", name: "ABC Logistics", entity_type: "ORG", aliases: [], sources: ["shipment_employee_statement.txt:r1"] },
  ],
  relationships: [
    { relationship_id: "REL-001", subject_id: "ENT-002", predicate: "works_for", object_id: "ENT-003", source: "shipment_employee_statement.txt:r1" },
    { relationship_id: "REL-002", subject_id: "ENT-002", predicate: "received", object_id: "ENT-001", source: "shipment_report_a.txt:r1" },
  ],
  claims: [
    claim("CLM-001", "ENT-001", "arrival_date", "14 September", "shipment_report_a.txt:r1"),
    claim("CLM-002", "ENT-001", "arrival_date", "16 September", "shipment_report_b.txt:r1"),
    claim("CLM-003", "ENT-002", "employer", "ABC Logistics", "shipment_employee_statement.txt:r1"),
  ],
  conflicts: [CONFLICT],
};

describe("a contradiction lights up all of its sides", () => {
  it("both claims, the entity, and the documents each side was read from", () => {
    expect([...conflictSpotlight(CONFLICT)].sort()).toEqual(
      ["CLM-001", "CLM-002", "DOC:shipment_report_a.txt", "DOC:shipment_report_b.txt", "ENT-001"].sort(),
    );
  });

  it("a citation's document node is the document, whatever the locator kind", () => {
    expect(documentNodeId("report.pdf:p3")).toBe("DOC:report.pdf");
    expect(documentNodeId("budget.csv")).toBe("DOC:budget.csv");
  });
});

describe("a selection knows its entity, so every view can follow it", () => {
  const view: KnowledgeGraphView = {
    run_id: "run_test",
    store: "memory",
    focus: null,
    depth: 0,
    nodes: [
      { id: "ENT-001", kind: "ENTITY", label: "Shipment 4821", entity_type: "SHIPMENT", parent: null, claim_count: 2, conflict_count: 1, grounded: true, source: "", status: "" },
      { id: "CLM-001", kind: "CLAIM", label: "arrival_date = 14 September", entity_type: null, parent: "ENT-001", claim_count: 0, conflict_count: 1, grounded: true, source: "a:r1", status: "" },
      { id: "DOC:a", kind: "DOCUMENT", label: "a", entity_type: null, parent: null, claim_count: 0, conflict_count: 0, grounded: true, source: "", status: "" },
    ],
    links: [],
  };

  it("an entity is its own, a claim is its parent's, a document belongs to none", () => {
    expect(entityOfSelection(view, "ENT-001")).toBe("ENT-001");
    expect(entityOfSelection(view, "CLM-001")).toBe("ENT-001");
    expect(entityOfSelection(view, "DOC:a")).toBeNull();
    expect(entityOfSelection(view, null)).toBeNull();
  });

  it("the timeline and contradiction lists narrow to the entity in focus", () => {
    const rows = [{ entity_id: "ENT-001" }, { entity_id: "ENT-002" }];
    expect(forEntity(rows, "ENT-002")).toEqual([{ entity_id: "ENT-002" }]);
    expect(forEntity(rows, null)).toHaveLength(2);
  });
});

describe("the timeline reads honestly", () => {
  it("never claims a year the text did not give", () => {
    expect(formatDate({ year: 2026, month: 9, day: 14 })).toBe("14 September 2026");
    expect(formatDate({ year: null, month: 9, day: 14 })).toBe("14 September (no year)");
    expect(formatDate({ year: 2026, month: 9, day: 16 }, true)).toBe("16 September 2026 (year inferred)");
    expect(formatDate(null)).toBe("undated");
  });

  it("relations and comparisons are words, not only colours", () => {
    expect(relationLabel("AFTER")).toBe("after the previous");
    expect(relationLabel(null)).toBe("first");
    expect(orderLabel("A_BEFORE_B")).toContain("before");
    expect(orderLabel("UNKNOWN")).toContain("cannot be told");
  });

  it("comparison holds two picks, and a third replaces the oldest", () => {
    expect(togglePick([], "CLM-001")).toEqual(["CLM-001"]);
    expect(togglePick(["CLM-001", "CLM-002"], "CLM-003")).toEqual(["CLM-002", "CLM-003"]);
    expect(togglePick(["CLM-001", "CLM-002"], "CLM-001")).toEqual(["CLM-002"]);
  });
});

describe("Member 3's investigation, built in the browser for an analysis", () => {
  it("finds the entity by name or alias, the way the backend resolves names", () => {
    expect(findEntity(SNAPSHOT, "the shipment #4821")?.entity_id).toBe("ENT-001");
    expect(findEntity(SNAPSHOT, "rahul  sharma")?.entity_id).toBe("ENT-002");
    expect(findEntity(SNAPSHOT, "nobody")).toBeNull();
  });

  it("gathers documents, claims, conflicts and the one-hop network", () => {
    const found = localInvestigation(SNAPSHOT, "Shipment 4821");
    expect(found).not.toBeNull();
    if (!found) return;
    expect(found.sources).toEqual(["shipment_report_a.txt", "shipment_report_b.txt"]);
    expect(found.claims.map((c) => c.claim_id)).toEqual(["CLM-001", "CLM-002"]);
    expect(found.conflicts).toEqual([CONFLICT]);
    expect(found.network.edges.map((e) => e.predicate)).toEqual(["received"]);
    expect(neighbourName(found, "ENT-002")).toBe("Rahul Sharma");
  });
});

describe("pages link to each other", () => {
  it("an entity opens its memory, and memory opens the graph on that entity", () => {
    expect(memoryLink("Rahul Sharma")).toBe("#/memory?entity=Rahul%20Sharma");
    expect(graphLink("run_abc", "Rahul Sharma")).toBe("#/mission/run_abc/graph?focus=Rahul%20Sharma");
    expect(graphLink("run_abc")).toBe("#/mission/run_abc/graph");
    expect(hashQuery("#/memory?entity=Rahul%20Sharma")).toEqual({ entity: "Rahul Sharma" });
    expect(hashQuery("#/memory")).toEqual({});
  });
});
