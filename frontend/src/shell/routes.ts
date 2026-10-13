/**
 * Routes, and where each one sits in the shell (Phase U3).
 *
 * Hash routing, deliberately: this app is served as static files next to an API, sometimes from a
 * file path, and a history-API router needs a server that rewrites unknown paths to index.html. A
 * hash works everywhere and a mission URL stays shareable.
 *
 * U3 merged pages that did the same thing under different names. The old addresses still work -
 * every page links to them - and now open inside the merged page, on the right tab:
 *
 * | Old address | Opens |
 * |---|---|
 * | `#/evidence`, `#/documents` | Library, on Evidence or Documents |
 * | `#/evaluation`, `#/memory`, `#/replay` | Insights, on Quality, Memory or Recordings |
 * | `#/audit` | Activity |
 *
 * Since U4 `#/` is the home page with the composer; the case list is `#/cases`.
 */

import { caseIdFromHash } from "../components/cases";
import { evidenceIdFromHash } from "../components/evidence";
import { hashQuery } from "../components/graph3d/investigation";

export type Route =
  | { name: "home" }
  | { name: "cases" }
  | { name: "case"; caseId: string }
  | { name: "list" }
  | { name: "new"; key: string }
  | { name: "documents"; workspace: string }
  | { name: "evidence"; evidenceId: string }
  | { name: "mission"; runId: string }
  | { name: "details"; runId: string }
  | { name: "graph"; runId: string; focus: string; search: string }
  | { name: "knowledge" }
  | { name: "memory"; entity: string }
  | { name: "replay" }
  | { name: "replayOne"; file: string }
  | { name: "evaluation" }
  | { name: "audit" }
  | { name: "design" }
  | { name: "attack"; runId: string };

export function parseRoute(full: string): Route {
  // Pages link to each other with a parameter (Phase 36): the graph opened on an entity
  // (`?focus=`), Memory opened on an entity (`?entity=`).
  const query = hashQuery(full);
  const hash = full.split("?")[0] ?? full;
  const attack = /^#\/mission\/([\w-]+)\/attack$/.exec(hash);
  if (attack?.[1]) return { name: "attack", runId: attack[1] };
  // Every panel of a run, as before U5; the evidence board (U6) replaces it.
  const details = /^#\/mission\/([\w-]+)\/details$/.exec(hash);
  if (details?.[1]) return { name: "details", runId: details[1] };
  const graph = /^#\/mission\/([\w-]+)\/graph$/.exec(hash);
  if (graph?.[1]) return { name: "graph", runId: graph[1], focus: query.focus ?? "", search: query.q ?? "" };
  if (hash === "#/knowledge") return { name: "knowledge" };
  if (hash === "#/memory") return { name: "memory", entity: query.entity ?? "" };
  const match = /^#\/mission\/([\w-]+)$/.exec(hash);
  if (match?.[1]) return { name: "mission", runId: match[1] };
  // New Mission may arrive filled in, from a search hit or a workspace (Phase 40).
  if (hash === "#/new") return { name: "new", key: full };
  if (hash === "#/evidence" || hash === "#/library" || evidenceIdFromHash(hash)) {
    return { name: "evidence", evidenceId: evidenceIdFromHash(hash) };
  }
  if (hash === "#/documents") return { name: "documents", workspace: query.workspace ?? "default" };
  if (hash === "#/replay") return { name: "replay" };
  // One recording, played back in the journal (U5).
  const replayOne = /^#\/replay\/(.+)$/.exec(hash);
  if (replayOne?.[1]) return { name: "replayOne", file: decodeURIComponent(replayOne[1]) };
  if (hash === "#/evaluation" || hash === "#/insights") return { name: "evaluation" };
  if (hash === "#/audit" || hash === "#/activity") return { name: "audit" };
  if (hash === "#/design") return { name: "design" };
  // Cases are the home page (Phase 44); the flat list of every investigation is `#/missions`.
  if (caseIdFromHash(hash)) return { name: "case", caseId: caseIdFromHash(hash) };
  if (hash === "#/missions") return { name: "list" };
  if (hash === "#/cases") return { name: "cases" };
  // Home: the composer (U4). The case list is `#/cases`.
  return { name: "home" };
}

/** The sidebar entry a route belongs to. */
export type Section = "new" | "cases" | "library" | "insights" | "activity" | "settings";

export function sectionOf(route: Route): Section {
  switch (route.name) {
    case "home":
    case "new":
    case "knowledge":
      return "new";
    case "evidence":
    case "documents":
      return "library";
    case "evaluation":
    case "memory":
    case "replay":
    case "replayOne":
      return "insights";
    case "audit":
      return "activity";
    case "design":
      return "settings";
    default:
      return "cases";
  }
}

/** The top bar's trail: where the page sits. The last item is the page itself. */
export function trailOf(route: Route): string[] {
  switch (route.name) {
    case "home":
      return ["Home"];
    case "cases":
      return ["Cases"];
    case "case":
      return ["Cases", route.caseId];
    case "list":
      return ["Cases", "All investigations"];
    case "new":
      return ["New investigation"];
    case "knowledge":
      return ["New investigation", "Quick analysis"];
    case "mission":
      return ["Investigations", route.runId];
    case "details":
      return ["Investigations", route.runId, "All details"];
    case "graph":
      return ["Investigations", route.runId, "Knowledge graph"];
    case "attack":
      return ["Investigations", route.runId, "Attack path"];
    case "evidence":
      return route.evidenceId ? ["Library", "Evidence", route.evidenceId] : ["Library", "Evidence"];
    case "documents":
      return ["Library", "Documents"];
    case "evaluation":
      return ["Insights", "Quality"];
    case "memory":
      return ["Insights", "Memory"];
    case "replay":
      return ["Insights", "Recordings"];
    case "replayOne":
      return ["Insights", "Recordings", "Replay"];
    case "audit":
      return ["Activity"];
    case "design":
      return ["Settings", "Design system"];
  }
}

export interface CaseLike {
  case: { case_id: string; title: string; opened_at: string; pinned?: boolean };
}

export interface CaseGroups<T> {
  pinned: T[];
  today: T[];
  week: T[];
  earlier: T[];
}

/** Sidebar groups: pinned first, then by when the case was opened. Order within a group is kept. */
export function groupCases<T extends CaseLike>(cases: T[], now: Date): CaseGroups<T> {
  const groups: CaseGroups<T> = { pinned: [], today: [], week: [], earlier: [] };
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const weekAgo = startOfToday - 6 * 24 * 60 * 60 * 1000;
  for (const item of cases) {
    if (item.case.pinned) {
      groups.pinned.push(item);
      continue;
    }
    const opened = Date.parse(item.case.opened_at);
    if (opened >= startOfToday) groups.today.push(item);
    else if (opened >= weekAgo) groups.week.push(item);
    else groups.earlier.push(item);
  }
  return groups;
}
