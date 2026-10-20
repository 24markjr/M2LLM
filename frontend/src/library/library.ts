/**
 * The Library (Phase U8), apart from React: one table of every file, its folders and its filters.
 *
 * A folder is a case: every file is filed under the case it belongs to, or is unfiled. That is the
 * grouping an investigator already uses, so the Library does not invent a second one. Filters
 * narrow the table; nothing here hides a file without the reason being one the person chose.
 */

import type { Case, EvidenceItem, IntegrityStatus } from "../api/types";

export interface LibraryRow {
  item: EvidenceItem;
  citations: number;
}

/** "all", "unfiled", or a case id. */
export type Folder = string;
export const ALL = "all";
export const UNFILED = "unfiled";

export interface Filters {
  folder: Folder;
  query: string;
  kind: string;
  integrity: IntegrityStatus | "";
  classification: string;
  citedOnly: boolean;
}

export const NO_FILTERS: Filters = { folder: ALL, query: "", kind: "", integrity: "", classification: "", citedOnly: false };

export function inFolder(row: LibraryRow, folder: Folder): boolean {
  if (folder === ALL) return true;
  if (folder === UNFILED) return !row.item.case_id;
  return row.item.case_id === folder;
}

/** Matches name, evidence id, SHA-256 prefix, source or who collected it; case-insensitive. */
export function matches(row: LibraryRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const { item } = row;
  return (
    item.name.toLowerCase().includes(q) ||
    item.evidence_id.toLowerCase().includes(q) ||
    item.sha256.startsWith(q) ||
    item.source.toLowerCase().includes(q) ||
    item.collected_by.toLowerCase().includes(q)
  );
}

export function filterRows(rows: LibraryRow[], f: Filters): LibraryRow[] {
  return rows.filter(
    (row) =>
      inFolder(row, f.folder) &&
      matches(row, f.query) &&
      (!f.kind || row.item.kind === f.kind) &&
      (!f.integrity || row.item.integrity === f.integrity) &&
      (!f.classification || row.item.classification === f.classification) &&
      (!f.citedOnly || row.citations > 0),
  );
}

export interface FolderEntry {
  id: Folder;
  label: string;
  count: number;
}

/**
 * All files, unfiled, then every case that holds a file or is open, by title. A case that holds
 * files but is missing from the case list (deleted, or the store is down) still gets its folder,
 * named by its id, so no file becomes unreachable.
 */
export function folders(rows: LibraryRow[], cases: Case[]): FolderEntry[] {
  const counts = new Map<string, number>();
  for (const r of rows) if (r.item.case_id) counts.set(r.item.case_id, (counts.get(r.item.case_id) ?? 0) + 1);
  const named = new Map(cases.map((c) => [c.case_id, c.title || c.case_id]));
  const ids = new Set([...cases.filter((c) => c.status !== "CLOSED").map((c) => c.case_id), ...counts.keys()]);
  const caseFolders = [...ids]
    .map((id) => ({ id, label: named.get(id) ?? id, count: counts.get(id) ?? 0 }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return [
    { id: ALL, label: "All files", count: rows.length },
    { id: UNFILED, label: "Unfiled", count: rows.filter((r) => !r.item.case_id).length },
    ...caseFolders,
  ];
}

/** The kinds present, for the kind filter. */
export function kindsOf(rows: LibraryRow[]): string[] {
  return [...new Set(rows.map((r) => r.item.kind).filter(Boolean))].sort();
}

export type SortKey = "collected" | "name" | "size" | "cited";

export function sortRows(rows: LibraryRow[], key: SortKey): LibraryRow[] {
  const out = [...rows];
  const by: Record<SortKey, (a: LibraryRow, b: LibraryRow) => number> = {
    collected: (a, b) => b.item.collected_at.localeCompare(a.item.collected_at),
    name: (a, b) => a.item.name.localeCompare(b.item.name),
    size: (a, b) => b.item.bytes - a.item.bytes,
    cited: (a, b) => b.citations - a.citations,
  };
  return out.sort(by[key]);
}
