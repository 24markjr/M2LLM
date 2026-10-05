/**
 * Small, pure rules behind the New Mission document picker (Phase 38), tested in Vitest.
 */

import type { FormatSpec } from "../api/types";

/** The file picker's `accept` attribute: exactly the extensions the engine reads. */
export function acceptAttribute(formats: FormatSpec[]): string {
  return formats.flatMap((f) => f.extensions).join(",");
}

/** Whether the engine reads this file at all, by extension. */
export function isSupported(name: string, formats: FormatSpec[]): boolean {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  const ext = name.slice(dot).toLowerCase();
  return formats.some((f) => f.extensions.includes(ext));
}

/**
 * A safe, unique file name for typed or pasted context: letters, digits, `-` and `_`, ending in
 * `.txt`, and not already taken (`context.txt`, then `context-2.txt`, ...).
 */
export function contextFileName(raw: string, taken: readonly string[]): string {
  const base =
    raw
      .trim()
      .replace(/\.txt$/i, "")
      .replace(/[^A-Za-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "context";
  let name = `${base}.txt`;
  for (let n = 2; taken.includes(name); n += 1) name = `${base}-${n}.txt`;
  return name;
}

/** "Word (.docx), Spreadsheet (.xlsx, .xlsm), ..." for the hint under the picker. */
export function formatsLine(formats: FormatSpec[]): string {
  return formats.map((f) => `${f.kind} (${f.extensions.join(", ")})`).join(" · ");
}

/** Bytes as a reader says them. */
export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
