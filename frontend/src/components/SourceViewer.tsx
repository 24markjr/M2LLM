/**
 * A citation opened in one click (v4 Phase 4): the document the claim cites, at the cited line,
 * highlighted and scrolled into view. Line citations (`report.txt:r12`) highlight the line; a page
 * citation (`report.pdf:p3`) opens the document at the start of the text it was read as.
 */

import { useEffect, useRef } from "react";

export function parseLocator(locator: string): { document: string; line: number | null } {
  const at = locator.lastIndexOf(":");
  if (at < 0) return { document: locator, line: null };
  const position = locator.slice(at + 1);
  const line = /^r\d+$/.test(position) ? Number(position.slice(1)) : null;
  return { document: locator.slice(0, at), line };
}

export function SourceViewer({
  texts,
  locator,
  onClose,
}: {
  texts: Record<string, string>;
  locator: string;
  onClose: () => void;
}) {
  const { document, line } = parseLocator(locator);
  const marked = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    marked.current?.scrollIntoView({ block: "center" });
  }, [locator]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const text = texts[document];
  return (
    <div className="source-drawer" role="dialog" aria-label={`Source ${locator}`}>
      <div className="source-drawer-head">
        <strong className="mono">{locator}</strong>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>
      {text === undefined ? (
        <p className="dim">This document's text is not available here.</p>
      ) : (
        <ol className="source-lines">
          {text.split("\n").map((content, i) => (
            <li key={i} ref={i + 1 === line ? marked : undefined} className={i + 1 === line ? "cited" : ""}>
              <span className="source-no">{i + 1}</span>
              <span>{content || " "}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
