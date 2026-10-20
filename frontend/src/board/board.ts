/**
 * The evidence board's logic (Phase U6), apart from React so it can be tested.
 *
 * - **Highlighting**: a citation is a character range in the text a file was read as (or a row,
 *   which is a line). The viewer splits the text into segments, each knowing which citations
 *   cover it, so the marked span is exactly what the finding rests on.
 * - **The pin board**: findings and the files they cite as pins, joined by strings. A string is
 *   drawn only for a connection the run actually holds - a shared cited line, a contradiction over
 *   the same file, the same explanation, a citation - never for a similarity guessed afterwards.
 */

import type { Finding, HypothesisSet, SourceLocator } from "../api/types";

export interface Range {
  start: number;
  end: number;
}

/** Where a locator points in `text`, or null when it cannot be placed (a page, or out of range). */
export function rangeOf(loc: SourceLocator, text: string): Range | null {
  if (loc.char_start !== null && loc.char_end !== null && loc.char_end > loc.char_start) {
    if (loc.char_start >= text.length) return null;
    return { start: loc.char_start, end: Math.min(loc.char_end, text.length) };
  }
  if (loc.row !== null && loc.row >= 1) {
    let start = 0;
    for (let line = 1; line < loc.row; line++) {
      const next = text.indexOf("\n", start);
      if (next === -1) return null;
      start = next + 1;
    }
    const end = text.indexOf("\n", start);
    return { start, end: end === -1 ? text.length : end };
  }
  return null;
}

/** The 1-based line a character offset falls on. */
export function lineOf(text: string, offset: number): number {
  let line = 1;
  for (let i = 0; i < offset && i < text.length; i++) if (text[i] === "\n") line++;
  return line;
}

export interface Mark {
  range: Range;
  /** The finding the citation belongs to. */
  findingId: string;
}

export interface Segment {
  text: string;
  /** The findings whose citations cover this segment; empty for unmarked text. */
  findings: string[];
}

/** The text cut at every mark boundary, each piece carrying the findings that cite it. */
export function segments(text: string, marks: Mark[]): Segment[] {
  const cuts = new Set<number>([0, text.length]);
  for (const m of marks) {
    cuts.add(m.range.start);
    cuts.add(m.range.end);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i + 1 < points.length; i++) {
    const start = points[i] as number;
    const end = points[i + 1] as number;
    if (end <= start) continue;
    const findings = marks.filter((m) => m.range.start <= start && m.range.end >= end).map((m) => m.findingId);
    out.push({ text: text.slice(start, end), findings: [...new Set(findings)] });
  }
  return out;
}

/** The document name a locator is keyed by in the run's sources. */
export function documentOf(loc: SourceLocator, sources: Record<string, string>): string {
  if (loc.document_name && loc.document_name in sources) return loc.document_name;
  if (loc.document_id in sources) return loc.document_id;
  return loc.document_name || loc.document_id;
}

/** Every citation into `document`, placed in its text. */
export function marksIn(document: string, findings: Finding[], sources: Record<string, string>): Mark[] {
  const text = sources[document];
  if (text === undefined) return [];
  const marks: Mark[] = [];
  for (const f of findings) {
    for (const ref of f.evidence) {
      if (documentOf(ref.locator, sources) !== document) continue;
      const range = rangeOf(ref.locator, text);
      if (range) marks.push({ range, findingId: f.finding_id });
    }
  }
  return marks;
}

// --- the pin board ------------------------------------------------------------------------------

export type PinKind = "finding" | "document";

export interface Pin {
  id: string;
  kind: PinKind;
  label: string;
  /** For a finding: its statement type; for a file: how many findings cite it. */
  detail: string;
}

export type StringKind = "same-line" | "contradiction" | "same-explanation" | "cites";

export interface PinString {
  from: string;
  to: string;
  kind: StringKind;
  why: string;
}

/** Strongest first: when two findings are connected more than one way, the string shows this one. */
const STRENGTH: StringKind[] = ["same-line", "contradiction", "same-explanation", "cites"];

export const STRING_LABEL: Record<StringKind, string> = {
  "same-line": "cite the same line",
  contradiction: "contradiction over the same file",
  "same-explanation": "bear on the same explanation",
  cites: "cites",
};

const docPin = (name: string) => `doc:${name}`;

function overlaps(a: Range, b: Range): boolean {
  return a.start < b.end && b.start < a.end;
}

export function pinsAndStrings(
  findings: Finding[],
  sources: Record<string, string>,
  hypotheses?: HypothesisSet | null,
): { pins: Pin[]; strings: PinString[] } {
  const cited = new Map<string, Set<string>>(); // finding -> documents
  const ranges = new Map<string, { document: string; range: Range | null }[]>();
  for (const f of findings) {
    const docs = new Set<string>();
    const placed: { document: string; range: Range | null }[] = [];
    for (const ref of f.evidence) {
      const document = documentOf(ref.locator, sources);
      docs.add(document);
      const text = sources[document];
      placed.push({ document, range: text === undefined ? null : rangeOf(ref.locator, text) });
    }
    cited.set(f.finding_id, docs);
    ranges.set(f.finding_id, placed);
  }

  const documents = new Map<string, number>();
  for (const docs of cited.values()) for (const d of docs) documents.set(d, (documents.get(d) ?? 0) + 1);

  const pins: Pin[] = [
    ...findings.map((f) => ({
      id: f.finding_id,
      kind: "finding" as const,
      label: f.claim,
      detail: (f.statement_type ?? f.classification).toLowerCase().replace(/_/g, " "),
    })),
    ...[...documents].map(([name, count]) => ({
      id: docPin(name),
      kind: "document" as const,
      label: name,
      detail: `${count} finding(s) cite it`,
    })),
  ];

  const best = new Map<string, PinString>();
  const offer = (s: PinString) => {
    const key = [s.from, s.to].sort().join("|");
    const held = best.get(key);
    if (!held || STRENGTH.indexOf(s.kind) < STRENGTH.indexOf(held.kind)) best.set(key, s);
  };

  for (let i = 0; i < findings.length; i++) {
    for (let j = i + 1; j < findings.length; j++) {
      const a = findings[i] as Finding;
      const b = findings[j] as Finding;
      const ra = ranges.get(a.finding_id) ?? [];
      const rb = ranges.get(b.finding_id) ?? [];
      const sameLine = ra.find((x) =>
        rb.some((y) => x.document === y.document && x.range && y.range && overlaps(x.range, y.range)),
      );
      if (sameLine) {
        offer({ from: a.finding_id, to: b.finding_id, kind: "same-line", why: `both cite the same line of ${sameLine.document}` });
      }
      const shared = [...(cited.get(a.finding_id) ?? [])].find((d) => cited.get(b.finding_id)?.has(d));
      if (shared && (a.statement_type === "CONTRADICTION" || b.statement_type === "CONTRADICTION")) {
        offer({ from: a.finding_id, to: b.finding_id, kind: "contradiction", why: `a contradiction over ${shared}` });
      }
    }
  }

  for (const h of hypotheses?.hypotheses ?? []) {
    const ids = [...h.supporting, ...h.contradicting].map((r) => r.finding_id).filter((id) => cited.has(id));
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        offer({ from: ids[i] as string, to: ids[j] as string, kind: "same-explanation", why: h.statement });
      }
    }
  }

  for (const [finding, docs] of cited) {
    for (const d of docs) offer({ from: finding, to: docPin(d), kind: "cites", why: `cites ${d}` });
  }

  return { pins, strings: [...best.values()] };
}

export interface Point {
  x: number;
  y: number;
}

/** Files along the top, findings in rows beneath: a readable start the person rearranges. */
export function initialLayout(pins: Pin[], width: number): Record<string, Point> {
  const out: Record<string, Point> = {};
  const columns = Math.max(1, Math.floor(width / 190));
  const place = (list: Pin[], top: number) =>
    list.forEach((p, i) => {
      out[p.id] = { x: 12 + (i % columns) * 190, y: top + Math.floor(i / columns) * 120 };
    });
  const docs = pins.filter((p) => p.kind === "document");
  place(docs, 12);
  place(
    pins.filter((p) => p.kind === "finding"),
    12 + Math.ceil(docs.length / columns) * 120 + 30,
  );
  return out;
}
