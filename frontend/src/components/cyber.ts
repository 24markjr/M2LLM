/** The cyber analysis as the console shows it (Phase 52). Pure, so it is tested without rendering. */

import type { CyberAnalysis, CyberRelation, PathEdge } from "../api/types";

/** "url http://… DELIVERED file C:\\…": an attack-path step in words. */
export function pathEdgeText(edge: PathEdge): string {
  const side = (value: string) => value.replace(":", " ");
  return `${side(edge.subject)} ${edge.predicate.replace(/_/g, " ")} ${side(edge.object)}`;
}

/** "account svc_admin LOGGED ON REMOTELY host srv-db". */
export function relationText(relation: CyberRelation): string {
  const side = (value: string) => value.replace(":", " ");
  return `${side(relation.subject)} ${relation.predicate.replace(/_/g, " ")} ${side(relation.object)}${
    relation.detail ? ` (${relation.detail})` : ""
  }`;
}

/** Indicators grouped by kind, kinds in a stable order. */
export function indicatorsByKind(analysis: CyberAnalysis): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const sighting of analysis.indicators) {
    const values = groups.get(sighting.kind) ?? [];
    values.push(sighting.value);
    groups.set(sighting.kind, values);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Whether there is anything to show: a run whose documents hold no events gets no panel. */
export function hasEvents(analysis: CyberAnalysis | null): boolean {
  return Boolean(analysis && analysis.events > 0);
}
