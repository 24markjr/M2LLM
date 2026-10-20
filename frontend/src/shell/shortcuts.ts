/**
 * Keyboard shortcuts (Phase U11), apart from React. Single keys, never with a modifier (Ctrl+K stays
 * the palette), and never while the person is typing: a shortcut that fires inside a text field
 * eats the letter they meant to type.
 */

export interface Shortcut {
  keys: string;
  label: string;
  /** Where it goes, or a named action the shell performs. */
  to: string;
}

export const SHORTCUTS: Shortcut[] = [
  { keys: "n", label: "New investigation", to: "#/" },
  { keys: "g c", label: "Go to cases", to: "#/cases" },
  { keys: "g l", label: "Go to the Library", to: "#/library" },
  { keys: "g i", label: "Go to Insights", to: "#/insights" },
  { keys: "g a", label: "Go to Activity", to: "#/activity" },
  { keys: "g s", label: "Go to Settings", to: "#/settings" },
  { keys: "/", label: "Search cases and pages", to: "search" },
  { keys: "?", label: "Show these shortcuts", to: "help" },
];

/** True when keys typed now would land in a field rather than drive the console. */
export function isTyping(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") return false;
  const el = target as HTMLElement;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable === true;
}

/**
 * The shortcut completed by `key`, given the key before it (`pending`, "" for none). Returns the
 * shortcut, or "pending" when `key` starts a two-key sequence, or null.
 */
export function resolveKey(key: string, pending: string): Shortcut | "pending" | null {
  const typed = pending ? `${pending} ${key}` : key;
  const hit = SHORTCUTS.find((s) => s.keys === typed);
  if (hit) return hit;
  if (!pending && SHORTCUTS.some((s) => s.keys.startsWith(`${key} `))) return "pending";
  return null;
}
