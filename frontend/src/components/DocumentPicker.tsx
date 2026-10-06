/**
 * The documents of a new mission (Phase 38): add files of any supported kind, type or paste context,
 * reuse earlier uploads, or pick an example.
 *
 * Every file is uploaded as soon as it is added, and the picker shows what it parsed as - its kind,
 * size, lines or pages, whether it carries an injection pattern - because a file that uploads
 * cleanly can still contribute nothing (an image before OCR, a video without a transcript). Those
 * are kept and listed, but not attached, so the mission is never started against silence.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { DragEvent } from "react";

import { ApiError, api } from "../api/client";
import type { FormatSpec, StoredDocument, UploadedDocument } from "../api/types";
import { acceptAttribute, contextFileName, formatsLine, isSupported, sizeLabel } from "./documents";

/** What the picker knows about an attached document, whatever it came from. */
interface Attached {
  name: string;
  kind: string;
  detail: string;
  injection: boolean;
}

export function DocumentPicker({
  examples,
  selected,
  onChange,
  workspace,
}: {
  examples: string[];
  selected: string[];
  onChange: (names: string[]) => void;
  /** Uploads are ingested into this workspace for search by meaning (Phase 40); `default` if absent. */
  workspace?: string | undefined;
}) {
  const [formats, setFormats] = useState<FormatSpec[]>([]);
  const [earlier, setEarlier] = useState<StoredDocument[]>([]);
  const [info, setInfo] = useState<Record<string, Attached>>({});
  const [waiting, setWaiting] = useState<UploadedDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [contextName, setContextName] = useState("");
  const [contextText, setContextText] = useState("");

  const refreshEarlier = useCallback(() => {
    api.listUploads().then(setEarlier).catch(() => setEarlier([]));
  }, []);

  useEffect(() => {
    api.getFormats().then(setFormats).catch(() => setFormats([]));
    refreshEarlier();
  }, [refreshEarlier]);

  const accept = useMemo(() => acceptAttribute(formats), [formats]);

  const toggle = (name: string) =>
    onChange(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name]);

  const upload = async (files: File[]) => {
    const unsupported = formats.length ? files.filter((f) => !isSupported(f.name, formats)) : [];
    const accepted = files.filter((f) => !unsupported.includes(f));
    setError(unsupported.length ? `Not a type the engine reads: ${unsupported.map((f) => f.name).join(", ")}` : "");
    if (!accepted.length) return;
    setBusy(true);
    try {
      const results = await api.uploadDocuments(accepted, workspace);
      const readable = results.filter((r) => r.has_text);
      setInfo((current) => {
        const next = { ...current };
        for (const r of results) {
          next[r.name] = {
            name: r.name,
            kind: r.kind,
            detail: `${sizeLabel(r.bytes)} · ${r.understood || r.summary}`,
            injection: Object.keys(r.injection.hits).length > 0,
          };
        }
        return next;
      });
      setWaiting((current) => [...current.filter((w) => !results.some((r) => r.name === w.name)), ...results.filter((r) => !r.has_text)]);
      onChange([...selected, ...readable.map((r) => r.name).filter((n) => !selected.includes(n))]);
      refreshEarlier();
    } catch (exc: unknown) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    } finally {
      setBusy(false);
    }
  };

  const addContext = () => {
    const text = contextText.trim();
    if (!text) return;
    const name = contextFileName(contextName, [...selected, ...earlier.map((e) => e.name)]);
    void upload([new File([text], name, { type: "text/plain" })]).then(() => {
      setContextText("");
      setContextName("");
    });
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDrag(false);
    void upload(Array.from(event.dataTransfer.files));
  };

  return (
    <div className="document-picker">
      {/* --- attached ------------------------------------------------------------------------ */}
      <div className="attached">
        {selected.length === 0 ? <div className="dim">No documents yet. Add files, type context, or pick an example.</div> : null}
        {selected.map((name) => {
          const known = info[name] ?? earlierInfo(earlier, name);
          return (
            <span key={name} className="chip">
              <span className="mono">{name}</span>
              {known ? <span className="dim"> · {known.kind}{known.detail ? ` · ${known.detail}` : ""}</span> : null}
              {known?.injection ? (
                <span className="badge v-contradicted" title="Text resembling a prompt injection: read as data, flagged">
                  injection pattern
                </span>
              ) : null}
              <button className="link" onClick={() => toggle(name)} aria-label={`remove ${name}`}>
                ✕
              </button>
            </span>
          );
        })}
      </div>

      {waiting.length ? (
        <div className="notice warn">
          Kept, but not attached until they have text:
          <ul>
            {waiting.map((w) => (
              <li key={w.name}>
                <span className="mono">{w.name}</span> - {w.note}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {error ? <div className="notice error">{error}</div> : null}

      {/* --- add files ------------------------------------------------------------------------ */}
      <label
        className={`drop-zone ${drag ? "over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <input
          type="file"
          multiple
          accept={accept}
          onChange={(e) => {
            void upload(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        <span>{busy ? "Uploading and reading." : "Add files - click, or drop them here"}</span>
        {formats.length ? <span className="dim">{formatsLine(formats)}</span> : null}
        <span className="dim">
          Images, scans, video and audio are understood on upload: text read, speech heard, and what
          they show described by a vision model - marked as seen, a model&apos;s account, weaker
          evidence than text that was read.
        </span>
      </label>

      {/* --- typed or pasted context ------------------------------------------------------------- */}
      <details className="typed-context">
        <summary>Type or paste context</summary>
        <input
          value={contextName}
          onChange={(e) => setContextName(e.target.value)}
          placeholder="A name for it, e.g. witness-notes (saved as a .txt document)"
          aria-label="Name for the typed context"
        />
        <textarea
          rows={5}
          value={contextText}
          onChange={(e) => setContextText(e.target.value)}
          placeholder="Notes, an email, a statement... It becomes a document the mission reads and cites line by line."
          aria-label="Typed context"
        />
        <button onClick={addContext} disabled={busy || !contextText.trim()}>
          Add as a document
        </button>
      </details>

      {/* --- earlier uploads, examples --------------------------------------------------------- */}
      {earlier.length ? (
        <div className="field">
          <label>Earlier uploads</label>
          <div className="row">
            {earlier.map((doc) => (
              <button key={doc.name} className={selected.includes(doc.name) ? "primary" : ""} onClick={() => toggle(doc.name)} title={`${doc.kind} · ${sizeLabel(doc.bytes)}`}>
                {selected.includes(doc.name) ? "✓ " : ""}
                {doc.name}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="field">
        <label>Examples</label>
        <div className="row">
          {examples.map((name) => (
            <button key={name} className={selected.includes(name) ? "primary" : ""} onClick={() => toggle(name)}>
              {selected.includes(name) ? "✓ " : ""}
              {name}
            </button>
          ))}
        </div>
      </div>

      {formats.length ? (
        <details className="dim">
          <summary>How each type is read</summary>
          <ul>
            {formats.map((f) => (
              <li key={f.kind}>
                <b>{f.kind}</b> <span className="mono">{f.extensions.join(" ")}</span>: {f.becomes}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function earlierInfo(earlier: StoredDocument[], name: string): Attached | null {
  const doc = earlier.find((e) => e.name === name);
  return doc ? { name, kind: doc.kind, detail: sizeLabel(doc.bytes), injection: false } : null;
}
