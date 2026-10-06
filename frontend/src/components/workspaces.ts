/**
 * Workspaces and stored retrieval (Phase 40), the pure part: names, links between the Documents
 * page and New Mission, and how a hit is shown. Kept free of React so it is tested directly.
 */

import { hashQuery } from "./graph3d/investigation";

export const DEFAULT_WORKSPACE = "default";

/** The server's rule for a workspace name: letters, digits, `-` and `_`, at most 64. */
export function validWorkspace(name: string): boolean {
  return /^[A-Za-z0-9_-]{1,64}$/.test(name);
}

/** What New Mission starts with when another page sends a person there. */
export interface MissionDraft {
  objective: string;
  documents: string[];
  workspace: string;
}

/** New Mission, filled in: from a search hit ("investigate this file") or a whole workspace. */
export function newMissionLink(draft: Partial<MissionDraft>): string {
  const parts: string[] = [];
  if (draft.objective) parts.push(`objective=${encodeURIComponent(draft.objective)}`);
  if (draft.documents?.length) parts.push(`documents=${draft.documents.map(encodeURIComponent).join(",")}`);
  if (draft.workspace) parts.push(`workspace=${encodeURIComponent(draft.workspace)}`);
  return `#/new${parts.length ? `?${parts.join("&")}` : ""}`;
}

/** The draft a `#/new?...` link carries. Absent fields stay absent so the page keeps its defaults. */
export function draftFromHash(hash: string): Partial<MissionDraft> {
  const query = hashQuery(hash);
  const draft: Partial<MissionDraft> = {};
  if (query.objective) draft.objective = query.objective;
  if (query.documents) {
    // `hashQuery` has decoded the whole value; names were encoded one by one, so a comma inside a
    // name arrives as a comma. File names here never contain one (the upload keeps the base name).
    const names = query.documents.split(",").filter(Boolean);
    if (names.length) draft.documents = names;
  }
  if (query.workspace && validWorkspace(query.workspace)) draft.workspace = query.workspace;
  return draft;
}

/** The Documents page, opened on one workspace. */
export function documentsLink(workspace?: string): string {
  return workspace && workspace !== DEFAULT_WORKSPACE
    ? `#/documents?workspace=${encodeURIComponent(workspace)}`
    : "#/documents";
}

/** The first 12 characters of a hash: enough to tell two versions of a file apart at a glance. */
export function shortHash(sha256: string): string {
  return sha256 ? sha256.slice(0, 12) : "-";
}

/** A score as a reader sees it. Cosine mapped to [0, 1]: 0.5 means unrelated. */
export function scoreLabel(score: number): string {
  return score.toFixed(3);
}

/** An objective that starts an investigation from a passage someone searched for. */
export function objectiveFromSearch(query: string): string {
  const text = query.trim();
  return text ? `Investigate: ${text}` : "";
}
