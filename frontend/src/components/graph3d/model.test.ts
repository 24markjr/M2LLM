/**
 * The 3D explorer's behaviour (Phase 32), tested without a browser.
 *
 * The first frontend tests in the repository. They cover what the user asked for: nodes with
 * sub-nodes, clicking a node lights up its related sub-nodes and neighbours, a finding lights up
 * its evidence, and nothing relies on colour alone.
 */

import { describe, expect, it } from "vitest";

import type { GraphLink, GraphNode, KnowledgeGraphView } from "../../api/types";
import {
  NO_FILTERS,
  colourOf,
  family,
  highlightSet,
  highlightedLinks,
  initialMode,
  linkKey,
  listOrder,
  parentsToExpand,
  particlesOf,
  searchEntities,
  shapeOf,
  shortLabel,
  visibleGraph,
} from "./model";

function node(id: string, kind: GraphNode["kind"], extra: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    kind,
    label: id,
    entity_type: kind === "ENTITY" ? "OTHER" : null,
    parent: null,
    claim_count: 0,
    conflict_count: 0,
    grounded: true,
    source: "",
    status: "",
    ...extra,
  };
}

function link(source: string, target: string, kind: GraphLink["kind"]): GraphLink {
  return { source, target, kind, label: "" };
}

/** Shipment 4821, two reports disagreeing on its arrival, Rahul Sharma who received it. */
const VIEW: KnowledgeGraphView = {
  run_id: "run_test",
  store: "memory",
  focus: null,
  depth: 0,
  nodes: [
    node("ENT-001", "ENTITY", { label: "Shipment 4821", entity_type: "SHIPMENT", claim_count: 2, conflict_count: 1 }),
    node("ENT-002", "ENTITY", { label: "Rahul Sharma", entity_type: "PERSON", claim_count: 1 }),
    node("ENT-003", "ENTITY", { label: "ABC Logistics", entity_type: "ORG" }),
    node("CLM-001", "CLAIM", { parent: "ENT-001", conflict_count: 1, label: "arrival_date = 14 September" }),
    node("CLM-002", "CLAIM", { parent: "ENT-001", conflict_count: 1, label: "arrival_date = 16 September" }),
    node("CLM-003", "CLAIM", { parent: "ENT-002", grounded: false, label: "shift = night" }),
    node("DOC:a.txt", "DOCUMENT"),
    node("DOC:b.txt", "DOCUMENT"),
    node("DOC:c.txt", "DOCUMENT"),
    node("F-001", "FINDING", { status: "SUPPORTED" }),
  ],
  links: [
    link("ENT-002", "ENT-001", "RELATES"),
    link("ENT-002", "ENT-003", "RELATES"),
    link("ENT-001", "CLM-001", "HAS_CLAIM"),
    link("ENT-001", "CLM-002", "HAS_CLAIM"),
    link("ENT-002", "CLM-003", "HAS_CLAIM"),
    link("CLM-001", "DOC:a.txt", "CITED_IN"),
    link("CLM-002", "DOC:b.txt", "CITED_IN"),
    link("CLM-003", "DOC:c.txt", "CITED_IN"),
    link("ENT-001", "DOC:a.txt", "MENTIONED_IN"),
    link("CLM-001", "CLM-002", "CONFLICTS_WITH"),
    link("F-001", "CLM-001", "CITES"),
    link("F-001", "CLM-002", "CITES"),
  ],
};

const ids = (nodes: GraphNode[]) => nodes.map((n) => n.id).sort();

describe("nodes with sub-nodes", () => {
  it("opens with entities only", () => {
    const graph = visibleGraph(VIEW, new Set());
    expect(ids(graph.nodes)).toEqual(["ENT-001", "ENT-002", "ENT-003"]);
    expect(graph.links.map((l) => l.kind)).toEqual(["RELATES", "RELATES"]);
  });

  it("expanding an entity shows its claims, their documents, and the findings citing them", () => {
    const graph = visibleGraph(VIEW, new Set(["ENT-001"]));
    expect(ids(graph.nodes)).toEqual(
      ["CLM-001", "CLM-002", "DOC:a.txt", "DOC:b.txt", "ENT-001", "ENT-002", "ENT-003", "F-001"].sort(),
    );
    expect(graph.links.some((l) => l.kind === "CONFLICTS_WITH")).toBe(true);
  });

  it("an entity's family is itself, its claims and their documents", () => {
    expect([...family(VIEW, "ENT-001")].sort()).toEqual(
      ["CLM-001", "CLM-002", "DOC:a.txt", "DOC:b.txt", "ENT-001"].sort(),
    );
    expect([...family(VIEW, "CLM-001")]).toEqual(["CLM-001"]);
  });
});

describe("clicking a node lights up what is related to it", () => {
  it("depth 1: the node, all its sub-nodes, and its direct neighbours", () => {
    const lit = highlightSet(VIEW, "ENT-001", 1);
    for (const id of ["ENT-001", "CLM-001", "CLM-002", "DOC:a.txt", "DOC:b.txt", "ENT-002", "F-001"]) {
      expect(lit.has(id)).toBe(true);
    }
    expect(lit.has("ENT-003")).toBe(false);
  });

  it("depth 2 reaches the neighbours of neighbours", () => {
    expect(highlightSet(VIEW, "ENT-001", 2).has("ENT-003")).toBe(true);
  });

  it("an unknown node lights nothing", () => {
    expect(highlightSet(VIEW, "ENT-999", 2).size).toBe(0);
  });

  it("lit links are those with both ends lit", () => {
    const lit = highlightSet(VIEW, "CLM-001", 1);
    const keys = highlightedLinks(VIEW.links, lit);
    expect(keys.has(linkKey(link("CLM-001", "CLM-002", "CONFLICTS_WITH")))).toBe(true);
    expect(keys.has(linkKey(link("ENT-002", "ENT-003", "RELATES")))).toBe(false);
  });

  it("knows which entities to expand so every lit claim can be seen", () => {
    const lit = highlightSet(VIEW, "F-001", 1);
    expect([...parentsToExpand(VIEW, lit)]).toEqual(["ENT-001"]);
  });
});

describe("filters", () => {
  it("conflicts only keeps entities with a conflict and their conflicting claims", () => {
    const graph = visibleGraph(VIEW, new Set(["ENT-001", "ENT-002"]), { ...NO_FILTERS, conflictsOnly: true });
    expect(ids(graph.nodes).filter((id) => !id.startsWith("DOC") && id !== "F-001")).toEqual([
      "CLM-001",
      "CLM-002",
      "ENT-001",
    ]);
  });

  it("grounded only hides claims the model wrote rather than read", () => {
    const graph = visibleGraph(VIEW, new Set(["ENT-002"]), { ...NO_FILTERS, groundedOnly: true });
    expect(graph.nodes.some((n) => n.id === "CLM-003")).toBe(false);
  });

  it("by entity type", () => {
    const graph = visibleGraph(VIEW, new Set(), { ...NO_FILTERS, entityTypes: new Set(["PERSON"]) });
    expect(ids(graph.nodes)).toEqual(["ENT-002"]);
  });

  it("by document", () => {
    const graph = visibleGraph(VIEW, new Set(["ENT-001"]), { ...NO_FILTERS, document: "b.txt" });
    expect(ids(graph.nodes)).toEqual(["CLM-002", "DOC:b.txt", "ENT-001", "F-001"].sort());
  });

  it("findings can be hidden", () => {
    const graph = visibleGraph(VIEW, new Set(["ENT-001"]), { ...NO_FILTERS, showFindings: false });
    expect(graph.nodes.some((n) => n.kind === "FINDING")).toBe(false);
  });
});

describe("search, keyboard list, drawing", () => {
  it("search puts the exact name first", () => {
    expect(searchEntities(VIEW, "rahul sharma").map((n) => n.id)).toEqual(["ENT-002"]);
    expect(searchEntities(VIEW, "  ")).toEqual([]);
  });

  it("the keyboard list puts each entity's claims under it", () => {
    const order = listOrder(visibleGraph(VIEW, new Set(["ENT-001"])));
    expect(order.slice(0, 5).map((n) => n.id)).toEqual(["ENT-003", "ENT-002", "ENT-001", "CLM-001", "CLM-002"]);
  });

  it("each kind has its own shape, so kind never relies on colour alone", () => {
    const shapes = new Set(["ENTITY", "CLAIM", "DOCUMENT", "FINDING"].map((k) => shapeOf(k as GraphNode["kind"])));
    expect(shapes.size).toBe(4);
  });

  it("a conflicting claim is red and its link carries moving particles", () => {
    expect(colourOf(VIEW.nodes[3] as GraphNode)).toBe("#f0616d");
    expect(particlesOf("CONFLICTS_WITH")).toBeGreaterThan(0);
    expect(particlesOf("HAS_CLAIM")).toBe(0);
  });

  it("labels drawn on the canvas are cut short; the tooltip keeps the full text", () => {
    expect(shortLabel("Rahul Sharma")).toBe("Rahul Sharma");
    const long = shortLabel("This report does not include the  cost of the delayed migration");
    expect(long.length).toBeLessThanOrEqual(28);
    expect(long.endsWith("…")).toBe(true);
  });

  it("falls back to 2D for reduced motion or no WebGL", () => {
    expect(initialMode(false, true)).toBe("3d");
    expect(initialMode(true, true)).toBe("2d");
    expect(initialMode(false, false)).toBe("2d");
  });
});
