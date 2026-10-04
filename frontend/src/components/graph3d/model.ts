/**
 * The 3D explorer's decisions, as pure functions (Phase 32).
 *
 * Everything the explorer decides - which nodes are visible, what lights up when a node is clicked,
 * what a finding's trail covers, how a node is drawn, the order of the keyboard list - lives here,
 * with no DOM and no WebGL. The canvas component only draws what these return. That split is what
 * makes the behaviour testable (`model.test.ts`, Vitest) when the canvas itself is not.
 *
 * Node hierarchy: **entities are parents; their claims are sub-nodes** (`parent`), shown when the
 * entity is expanded. Documents appear beside an expanded entity's claims. Findings are an overlay.
 */

import type { GraphLink, GraphLinkKind, GraphNode, GraphNodeKind, KnowledgeGraphView } from "../../api/types";

export interface Filters {
  /** Entity types to show; empty means all. */
  entityTypes: ReadonlySet<string>;
  /** Only entities with a conflict, and only their conflicting claims. */
  conflictsOnly: boolean;
  /** Hide claims whose value was not found on their cited line. */
  groundedOnly: boolean;
  /** Only what is tied to this document. */
  document: string | null;
  /** Show findings and their CITES links. */
  showFindings: boolean;
}

export const NO_FILTERS: Filters = {
  entityTypes: new Set<string>(),
  conflictsOnly: false,
  groundedOnly: false,
  document: null,
  showFindings: true,
};

export interface VisibleGraph {
  nodes: GraphNode[];
  links: GraphLink[];
}

export const DOC_PREFIX = "DOC:";

/** What is on screen, given which entities are expanded and the filters. */
export function visibleGraph(
  view: KnowledgeGraphView,
  expanded: ReadonlySet<string>,
  filters: Filters = NO_FILTERS,
): VisibleGraph {
  const conflictClaims = new Set(
    view.links.filter((l) => l.kind === "CONFLICTS_WITH").flatMap((l) => [l.source, l.target]),
  );
  const docOf = new Map<string, string>(
    view.links.filter((l) => l.kind === "CITED_IN").map((l) => [l.source, l.target]),
  );
  const docsOfEntity = new Map<string, Set<string>>();
  for (const link of view.links) {
    if (link.kind === "MENTIONED_IN") addTo(docsOfEntity, link.source, link.target);
  }
  for (const node of view.nodes) {
    if (node.kind === "CLAIM" && node.parent) {
      const doc = docOf.get(node.id);
      if (doc) addTo(docsOfEntity, node.parent, doc);
    }
  }
  const wantedDoc = filters.document ? `${DOC_PREFIX}${filters.document}` : null;

  const entities = view.nodes.filter(
    (n) =>
      n.kind === "ENTITY" &&
      (filters.entityTypes.size === 0 || filters.entityTypes.has(n.entity_type ?? "OTHER")) &&
      (!filters.conflictsOnly || n.conflict_count > 0) &&
      (!wantedDoc || docsOfEntity.get(n.id)?.has(wantedDoc) === true),
  );
  const shownEntities = new Set(entities.map((n) => n.id));

  const claims = view.nodes.filter(
    (n) =>
      n.kind === "CLAIM" &&
      n.parent !== null &&
      shownEntities.has(n.parent) &&
      expanded.has(n.parent) &&
      (!filters.groundedOnly || n.grounded) &&
      (!filters.conflictsOnly || conflictClaims.has(n.id)) &&
      (!wantedDoc || docOf.get(n.id) === wantedDoc),
  );
  const shownClaims = new Set(claims.map((n) => n.id));

  const documents = new Set<string>();
  for (const claim of claims) {
    const doc = docOf.get(claim.id);
    if (doc) documents.add(doc);
  }
  for (const entity of entities) {
    if (!expanded.has(entity.id)) continue;
    for (const doc of docsOfEntity.get(entity.id) ?? []) {
      if (!wantedDoc || doc === wantedDoc) documents.add(doc);
    }
  }

  const findings = filters.showFindings
    ? view.nodes.filter(
        (n) =>
          n.kind === "FINDING" &&
          view.links.some(
            (l) =>
              l.source === n.id &&
              l.kind === "CITES" &&
              (shownClaims.has(l.target) || documents.has(l.target)),
          ),
      )
    : [];

  const nodes = [
    ...entities,
    ...claims,
    ...view.nodes.filter((n) => n.kind === "DOCUMENT" && documents.has(n.id)),
    ...findings,
  ];
  const ids = new Set(nodes.map((n) => n.id));
  const links = view.links.filter((l) => ids.has(l.source) && ids.has(l.target));
  return { nodes, links };
}

/** An entity's sub-nodes: its claims and the documents they and it are cited in. */
export function family(view: KnowledgeGraphView, nodeId: string): Set<string> {
  const members = new Set<string>([nodeId]);
  const node = view.nodes.find((n) => n.id === nodeId);
  if (node?.kind !== "ENTITY") return members;
  for (const claim of view.nodes) {
    if (claim.kind === "CLAIM" && claim.parent === nodeId) members.add(claim.id);
  }
  for (const link of view.links) {
    if (link.kind === "MENTIONED_IN" && link.source === nodeId) members.add(link.target);
    if (link.kind === "CITED_IN" && members.has(link.source)) members.add(link.target);
  }
  return members;
}

/**
 * What lights up when a node is clicked: the node, all its sub-nodes, and everything within
 * `depth` hops of them in either direction, over every kind of link.
 *
 * Depth 1 is the node, its claims and documents, and its direct neighbours; depth 2 adds their
 * neighbours. Computed over the whole graph, not only what is on screen, so a highlight can reach
 * a node inside a collapsed entity, and expanding it then shows that node lit.
 */
export function highlightSet(view: KnowledgeGraphView, nodeId: string, depth: number): Set<string> {
  const reached = family(view, nodeId);
  if (!view.nodes.some((n) => n.id === nodeId)) return new Set();
  const adjacent = adjacency(view.links);
  let frontier = new Set(reached);
  for (let hop = 0; hop < Math.max(0, depth); hop += 1) {
    const next = new Set<string>();
    for (const id of frontier) {
      for (const neighbour of adjacent.get(id) ?? []) {
        if (!reached.has(neighbour)) next.add(neighbour);
      }
    }
    if (next.size === 0) break;
    for (const id of next) reached.add(id);
    frontier = next;
  }
  return reached;
}

/** The links whose both ends are lit. */
export function highlightedLinks(links: GraphLink[], lit: ReadonlySet<string>): Set<string> {
  return new Set(links.filter((l) => lit.has(l.source) && lit.has(l.target)).map(linkKey));
}

export function linkKey(link: Pick<GraphLink, "source" | "target" | "kind">): string {
  return `${link.source}|${link.kind}|${link.target}`;
}

/** Entities that must be expanded for every node of a highlight to be visible. */
export function parentsToExpand(view: KnowledgeGraphView, ids: ReadonlySet<string>): Set<string> {
  const parents = new Set<string>();
  for (const node of view.nodes) {
    if (node.kind === "CLAIM" && node.parent && ids.has(node.id)) parents.add(node.parent);
  }
  return parents;
}

/** Entity search for the fly-to box: case-insensitive substring, exact match first. */
export function searchEntities(view: KnowledgeGraphView, query: string): GraphNode[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return view.nodes
    .filter((n) => n.kind === "ENTITY" && n.label.toLowerCase().includes(needle))
    .sort(
      (a, b) =>
        Number(b.label.toLowerCase() === needle) - Number(a.label.toLowerCase() === needle) ||
        a.label.length - b.label.length,
    );
}

/** The keyboard list: entities by name, each followed by its visible claims. */
export function listOrder(graph: VisibleGraph): GraphNode[] {
  const entities = graph.nodes
    .filter((n) => n.kind === "ENTITY")
    .sort((a, b) => a.label.localeCompare(b.label));
  const ordered: GraphNode[] = [];
  for (const entity of entities) {
    ordered.push(entity);
    ordered.push(...graph.nodes.filter((n) => n.kind === "CLAIM" && n.parent === entity.id));
  }
  ordered.push(...graph.nodes.filter((n) => n.kind === "DOCUMENT" || n.kind === "FINDING"));
  return ordered;
}

// --- drawing: shape, colour and size, never colour alone -----------------------------------------

export type Shape = "sphere" | "cube" | "octahedron" | "tetrahedron";

/** Kind is shown by shape as well as colour (Phase 21's rule: nothing relies on colour alone). */
export function shapeOf(kind: GraphNodeKind): Shape {
  return ({ ENTITY: "sphere", CLAIM: "cube", DOCUMENT: "octahedron", FINDING: "tetrahedron" } as const)[
    kind
  ];
}

const ENTITY_COLOURS: Record<string, string> = {
  PERSON: "#4da3ff",
  ORG: "#b48cff",
  LOCATION: "#3ecf8e",
  DATE: "#e8b34a",
  PRODUCT: "#ff8ac1",
  SHIPMENT: "#5ad8e6",
  OTHER: "#8b95a8",
};

export function colourOf(node: GraphNode): string {
  switch (node.kind) {
    case "ENTITY":
      return ENTITY_COLOURS[node.entity_type ?? "OTHER"] ?? "#8b95a8";
    case "CLAIM":
      if (node.conflict_count > 0) return "#f0616d";
      return node.grounded ? "#c9d1df" : "#5c6578";
    case "DOCUMENT":
      return "#7c86a0";
    case "FINDING":
      return node.status === "SUPPORTED" ? "#3ecf8e" : node.status ? "#e8b34a" : "#7c86a0";
  }
}

/** Relative size: an entity grows with the claims it carries. */
/** A label short enough to draw beside a node; the full text is in the tooltip and the panel. */
export function shortLabel(label: string, max = 28): string {
  const clean = label.replace(/\s+/g, " ").trim();
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`;
}

export function sizeOf(node: GraphNode): number {
  if (node.kind === "ENTITY") return 4 + Math.min(node.claim_count, 12);
  if (node.kind === "FINDING") return 5;
  return 2;
}

export function linkColourOf(kind: GraphLinkKind): string {
  if (kind === "CONFLICTS_WITH") return "#f0616d";
  if (kind === "CITES") return "#3ecf8e";
  if (kind === "RELATES") return "#4da3ff";
  return "#333d52";
}

/** Directional particles move along conflicts, so a contradiction is visible in motion too. */
export function particlesOf(kind: GraphLinkKind): number {
  return kind === "CONFLICTS_WITH" ? 4 : 0;
}

/** 2D when motion is unwelcome or WebGL is missing. */
export function initialMode(prefersReducedMotion: boolean, hasWebGL: boolean): "2d" | "3d" {
  return prefersReducedMotion || !hasWebGL ? "2d" : "3d";
}

function adjacency(links: GraphLink[]): Map<string, Set<string>> {
  const adjacent = new Map<string, Set<string>>();
  for (const link of links) {
    addTo(adjacent, link.source, link.target);
    addTo(adjacent, link.target, link.source);
  }
  return adjacent;
}

function addTo(map: Map<string, Set<string>>, key: string, value: string): void {
  const set = map.get(key);
  if (set) set.add(value);
  else map.set(key, new Set([value]));
}

// --- memory across missions (Phase 33) --------------------------------------------------------

/**
 * What the pop-up says about an entity's past, from the missions memory saw it in.
 *
 * `runs` is null when memory could not answer (off, or unreachable): then nothing is said, because
 * "first seen here" would be a claim memory did not make. An entity memory has no record of
 * (`runs` empty) is new to memory.
 */
export function recallText(runs: readonly string[] | null, current: string | null): string {
  if (runs === null) return "";
  const earlier = runs.filter((run) => run !== current).length;
  if (earlier === 0) return current ? "first seen in this mission" : "not seen in any stored mission";
  const missions = earlier === 1 ? "mission" : "missions";
  return current ? `seen in ${earlier} earlier ${missions}` : `seen in ${earlier} stored ${missions}`;
}
