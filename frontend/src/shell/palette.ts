/**
 * What Ctrl+K can open (Phase U3): the places in the console, filtered by the words typed. Cases
 * come from the API's case search and are listed after these.
 */

export interface PaletteEntry {
  label: string;
  hint: string;
  href: string;
}

export const PLACES: PaletteEntry[] = [
  { label: "New investigation", hint: "Ask a question over your files", href: "#/new" },
  { label: "Quick analysis", hint: "Entities, claims and conflicts, without a full investigation", href: "#/knowledge" },
  { label: "Cases", hint: "Every case", href: "#/" },
  { label: "All investigations", hint: "Every investigation, in a case or not", href: "#/missions" },
  { label: "Library: evidence", hint: "Every file, its hash and chain of custody", href: "#/evidence" },
  { label: "Library: documents", hint: "Workspaces searched by meaning", href: "#/documents" },
  { label: "Insights: quality", hint: "The quality score and its trend", href: "#/evaluation" },
  { label: "Insights: memory", hint: "What earlier investigations found", href: "#/memory" },
  { label: "Insights: recordings", hint: "Replay a finished investigation", href: "#/replay" },
  { label: "Activity", hint: "The audit log", href: "#/activity" },
  { label: "Design system", hint: "Every component, in the current theme", href: "#/design" },
];

/** Places whose label or hint contains every word typed. All of them when nothing is typed. */
export function matchPlaces(query: string, places: PaletteEntry[] = PLACES): PaletteEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return places;
  return places.filter((p) => {
    const text = `${p.label} ${p.hint}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
}
