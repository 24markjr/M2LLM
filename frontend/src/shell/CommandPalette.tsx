/**
 * Search everything (Ctrl+K, Phase U3): places in the console and cases - by id, title, description
 * or a question asked in them. Arrow keys move, Enter opens, Escape closes.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { api } from "../api/client";
import { Dialog } from "../ui/components";
import { IconFolder, IconSearch } from "../ui/icons";
import { matchPlaces, type PaletteEntry } from "./palette";

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [cases, setCases] = useState<PaletteEntry[]>([]);
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    window.setTimeout(() => input.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open || !query.trim()) {
      setCases([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api
        .listCases(query.trim())
        .then((body) =>
          setCases(
            body.cases.slice(0, 8).map(({ case: c }) => ({
              label: c.title,
              hint: c.case_id,
              href: `#/case/${c.case_id}`,
            })),
          ),
        )
        .catch(() => setCases([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [open, query]);

  const results = [...matchPlaces(query), ...cases];
  const go = (entry: PaletteEntry | undefined) => {
    if (!entry) return;
    window.location.hash = entry.href;
    onClose();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[index]);
    }
  };

  return (
    <Dialog open={open} title="Search" onClose={onClose}>
      <div className="palette">
        <div className="palette-input">
          <IconSearch size={18} />
          <input
            ref={input}
            value={query}
            placeholder="A case, a question asked, or a page"
            aria-label="Search"
            aria-controls="palette-results"
            aria-activedescendant={results[index] ? `palette-${index}` : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
            onKeyDown={onKey}
          />
        </div>
        <ul id="palette-results" role="listbox" className="palette-results">
          {results.map((entry, i) => (
            <li
              key={`${entry.href}-${i}`}
              id={`palette-${i}`}
              role="option"
              aria-selected={i === index}
              className={i === index ? "on" : ""}
              onMouseEnter={() => setIndex(i)}
              onClick={() => go(entry)}
            >
              {entry.href.startsWith("#/case/") ? <IconFolder size={16} /> : null}
              <span className="palette-label">{entry.label}</span>
              <span className="palette-hint">{entry.hint}</span>
            </li>
          ))}
          {results.length === 0 ? <li className="palette-empty">Nothing matches.</li> : null}
        </ul>
      </div>
    </Dialog>
  );
}
