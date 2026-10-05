/**
 * Member 3's investigation views, as logic (Phase 36). No React, no network: tested in Vitest.
 *
 * Member 3's dashboard had three separate modes: investigate an entity, hybrid search, and show all
 * contradictions. Here they are one workbench, and the owner's rule for it is that **everything is
 * interrelated**: every row in every view leads somewhere else - a claim to its node in the graph,
 * an entity name to its investigate card, a contradiction to all of its sides lit at once, an entity
 * to its memory across missions, and back. The functions below are what those links resolve to.
 */

import type {
  ClaimConflict,
  ClaimOrder,
  EntityInvestigation,
  EntityNetwork,
  KnowledgeEntity,
  KnowledgeGraphView,
  KnowledgeSnapshot,
  PartialDate,
  TimelineRelation,
} from "../../api/types";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** The graph's node id for the document a citation points into (`report.txt:r4` -> `DOC:report.txt`). */
export function documentNodeId(source: string): string {
  const cut = source.lastIndexOf(":");
  return `DOC:${cut > 0 ? source.slice(0, cut) : source}`;
}

/**
 * What a contradiction lights up: every claim on every side, the entity they are about, and each
 * document a side was read from - the same shape as a finding's evidence trail.
 */
export function conflictSpotlight(conflict: ClaimConflict): Set<string> {
  const ids = new Set<string>([conflict.entity_id]);
  for (const side of conflict.sides) {
    side.claim_ids.forEach((id) => ids.add(id));
    side.sources.forEach((source) => ids.add(documentNodeId(source)));
  }
  return ids;
}

/** The entity a graph selection belongs to: the entity itself, or a claim's parent. */
export function entityOfSelection(view: KnowledgeGraphView, nodeId: string | null): string | null {
  if (!nodeId) return null;
  const node = view.nodes.find((n) => n.id === nodeId);
  if (!node) return null;
  if (node.kind === "ENTITY") return node.id;
  if (node.kind === "CLAIM") return node.parent;
  return null;
}

/** A date as written, and never more precise than the text: a missing year says so. */
export function formatDate(date: PartialDate | null, yearInferred = false): string {
  if (!date) return "undated";
  const month = MONTHS[date.month - 1] ?? `month ${date.month}`;
  const day = date.day ? `${date.day} ` : "";
  if (date.year === null) return `${day}${month} (no year)`;
  return `${day}${month} ${date.year}${yearInferred ? " (year inferred)" : ""}`;
}

/** Member 3's `relation_to_previous`, in words. A label, not only a colour. */
export function relationLabel(relation: TimelineRelation | null): string {
  if (relation === "AFTER") return "after the previous";
  if (relation === "SAME_TIME_AS") return "same time as the previous";
  if (relation === "UNKNOWN") return "order unknown";
  return "first";
}

/** Member 3's `/timeline/compare` result, as a sentence about the two picked events. */
export function orderLabel(order: ClaimOrder): string {
  if (order === "A_BEFORE_B") return "the first happened before the second";
  if (order === "A_AFTER_B") return "the first happened after the second";
  if (order === "SAME_TIME") return "they happened at the same time";
  return "their order cannot be told from the dates given";
}

/** Rows belonging to one entity, or every row when no entity is in focus. */
export function forEntity<T extends { entity_id: string }>(rows: T[], entityId: string | null): T[] {
  return entityId ? rows.filter((row) => row.entity_id === entityId) : rows;
}

/** Up to two timeline events picked for comparison; picking a third drops the oldest pick. */
export function togglePick(picked: string[], claimId: string): string[] {
  if (picked.includes(claimId)) return picked.filter((id) => id !== claimId);
  return [...picked, claimId].slice(-2);
}

function key(name: string): string {
  const folded = name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return folded.startsWith("the ") ? folded.slice(4) : folded;
}

/** An entity by name or alias, matched the way the backend resolves names. */
export function findEntity(snapshot: KnowledgeSnapshot, name: string): KnowledgeEntity | null {
  const wanted = key(name);
  if (!wanted) return null;
  return (
    snapshot.entities.find((e) => key(e.name) === wanted || e.aliases.some((a) => key(a) === wanted)) ?? null
  );
}

/**
 * Member 3's `/investigation/{name}`, built in the browser from a knowledge base that is not stored
 * (the analysis page). The same fields as the endpoint; the network is one hop, as the endpoint's
 * default.
 */
export function localInvestigation(snapshot: KnowledgeSnapshot, name: string): EntityInvestigation | null {
  const entity = findEntity(snapshot, name);
  if (!entity) return null;
  const claims = snapshot.claims.filter((c) => c.entity_id === entity.entity_id);
  const edges = snapshot.relationships
    .filter((r) => r.subject_id === entity.entity_id || r.object_id === entity.entity_id)
    .map((r) => ({ from_id: r.subject_id, to_id: r.object_id, predicate: r.predicate, source: r.source }));
  const neighbours = new Set([entity.entity_id, ...edges.flatMap((e) => [e.from_id, e.to_id])]);
  const network: EntityNetwork = {
    center_id: entity.entity_id,
    depth: 1,
    nodes: snapshot.entities
      .filter((e) => neighbours.has(e.entity_id))
      .map((e) => ({ entity_id: e.entity_id, name: e.name, entity_type: e.entity_type })),
    edges,
  };
  const documents = new Set([...entity.sources, ...claims.map((c) => c.source)].map(documentOf));
  return {
    entity,
    sources: [...documents].sort(),
    network,
    claims,
    conflicts: snapshot.conflicts.filter((k) => k.entity_id === entity.entity_id),
  };
}

function documentOf(source: string): string {
  const cut = source.lastIndexOf(":");
  return cut > 0 ? source.slice(0, cut) : source;
}

/** The name of an entity id inside an investigation's network, for "connected to" rows. */
export function neighbourName(investigation: EntityInvestigation, entityId: string): string {
  return investigation.network.nodes.find((n) => n.entity_id === entityId)?.name ?? entityId;
}

// --- links between pages ----------------------------------------------------------------------

/** The Memory page, with an entity already looked up. */
export function memoryLink(name: string): string {
  return `#/memory?entity=${encodeURIComponent(name)}`;
}

/** A mission's knowledge graph, opened on one entity. */
export function graphLink(runId: string, entityName?: string): string {
  return `#/mission/${runId}/graph${entityName ? `?focus=${encodeURIComponent(entityName)}` : ""}`;
}

/** A mission's knowledge graph with the workbench already searching for `text` (Phase 37). */
export function graphSearchLink(runId: string, text: string): string {
  return `#/mission/${runId}/graph?q=${encodeURIComponent(text)}`;
}

/** `name=value` pairs after a hash route's `?`. */
export function hashQuery(hash: string): Record<string, string> {
  const at = hash.indexOf("?");
  if (at < 0) return {};
  const out: Record<string, string> = {};
  for (const pair of hash.slice(at + 1).split("&")) {
    const [name, value = ""] = pair.split("=");
    if (name) out[decodeURIComponent(name)] = decodeURIComponent(value);
  }
  return out;
}
