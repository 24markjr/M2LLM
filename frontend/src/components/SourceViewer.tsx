/**
 * A citation opened in one click (v4 Phase 4): the document the claim cites, at the cited line,
 * highlighted and scrolled into view. Line citations (`report.txt:r12`) highlight the line; a page
 * citation (`report.pdf:p3`) opens the document at the start of the text it was read as.
 *
 * A document in an Indian language (v4 Phase 6) opens as two aligned columns - the original, which
 * is the evidence, and the English translation the investigation read - with the cited line
 * highlighted in both. Line N of one is line N of the other.
 */

import { useEffect, useRef, type RefObject } from "react";

import type { DocumentLanguage } from "../api/types";

export function parseLocator(locator: string): { document: string; line: number | null } {
  const at = locator.lastIndexOf(":");
  if (at < 0) return { document: locator, line: null };
  const position = locator.slice(at + 1);
  const line = /^r\d+$/.test(position) ? Number(position.slice(1)) : null;
  return { document: locator.slice(0, at), line };
}

const MARKER = /^\[translated:[a-z]+\]\s*/;

/** The translation's line without its marker: the column heading already says it is one. */
export function withoutMarker(line: string): string {
  return line.replace(MARKER, "");
}

export function SourceViewer({
  texts,
  locator,
  onClose,
  originals = {},
}: {
  texts: Record<string, string>;
  locator: string;
  onClose: () => void;
  originals?: Record<string, DocumentLanguage>;
}) {
  const { document, line } = parseLocator(locator);
  const marked = useRef<HTMLElement | null>(null);
  useEffect(() => {
    marked.current?.scrollIntoView({ block: "center" });
  }, [locator]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const text = texts[document];
  const reading = originals[document];
  const bilingual = reading && reading.original_text && reading.translated_lines.length > 0;
  return (
    <div className={`source-drawer${bilingual ? " bilingual" : ""}`} role="dialog" aria-label={`Source ${locator}`}>
      <div className="source-drawer-head">
        <strong className="mono">{locator}</strong>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>
      {text === undefined ? (
        <p className="dim">This document's text is not available here.</p>
      ) : bilingual ? (
        <Bilingual text={text} reading={reading} line={line} marked={marked} />
      ) : (
        <ol className="source-lines">
          {text.split("\n").map((content, i) => (
            <li
              key={i}
              ref={i + 1 === line ? (el) => void (marked.current = el) : undefined}
              className={i + 1 === line ? "cited" : ""}
            >
              <span className="source-no">{i + 1}</span>
              <span>{content || " "}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Bilingual({
  text,
  reading,
  line,
  marked,
}: {
  text: string;
  reading: DocumentLanguage;
  line: number | null;
  marked: RefObject<HTMLElement | null>;
}) {
  const original = reading.original_text.split("\n");
  const english = text.split("\n");
  const translated = new Set(reading.translated_lines);
  const unsafe = new Set(reading.unsafe_lines);
  const citedUnsafe = line !== null && unsafe.has(line);
  return (
    <>
      <p className="dim source-language">
        Written in {reading.language_name || reading.language}. The original is the evidence; the English is a machine
        translation by {reading.engine} <span className="mono">{reading.engine_version}</span>, line for line.
        {reading.untranslated_lines ? ` ${reading.untranslated_lines} line(s) past the limit were not translated.` : ""}
      </p>
      {citedUnsafe ? (
        <p className="source-warning">The figures on the cited line did not all survive translation - check the original.</p>
      ) : null}
      <table className="source-pair">
        <thead>
          <tr>
            <th className="source-no">#</th>
            <th lang={reading.language}>Original ({reading.language_name || reading.language})</th>
            <th>English translation</th>
          </tr>
        </thead>
        <tbody>
          {original.map((content, i) => {
            const n = i + 1;
            const cited = n === line;
            return (
              <tr
                key={i}
                ref={cited ? (el) => void (marked.current = el) : undefined}
                className={[cited ? "cited" : "", unsafe.has(n) ? "unsafe" : ""].join(" ").trim()}
              >
                <td className="source-no">{n}</td>
                <td lang={reading.language}>{content || " "}</td>
                <td className={translated.has(n) ? "" : "dim"}>{withoutMarker(english[i] ?? "") || " "}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
