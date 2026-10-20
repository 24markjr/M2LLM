/**
 * The Library (Phase U8): one table of every file, its folders (cases), filters, and a custody
 * drawer. Selecting a row opens the drawer beside the table: identity, integrity with re-verify,
 * the chain of custody, the findings that cite it, other versions, filing, and the original.
 * The full item page (`#/evidence/EV-…`) is still one click away.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import type { Case, EvidenceDetail, EvidenceList } from "../api/types";
import { CLASSIFICATIONS, custodyLabel, custodySummary, evidenceLink } from "../components/evidence";
import { sizeLabel } from "../components/documents";
import { casesChanged } from "../shell/Sidebar";
import { Badge, Button, Notice, useToast, type Tone } from "../ui/components";
import {
  ALL,
  filterRows,
  folders,
  kindsOf,
  NO_FILTERS,
  sortRows,
  UNFILED,
  type Filters,
  type LibraryRow,
  type SortKey,
} from "./library";
import "./library.css";

const INTEGRITY_TONE: Record<string, Tone> = { VERIFIED: "verified", FAILED: "unsupported", UNCHECKED: "unknown" };

function errorText(exc: unknown): string {
  return exc instanceof ApiError ? exc.message : "Something went wrong.";
}

export function LibraryPage() {
  const notify = useToast();
  const [list, setList] = useState<EvidenceList | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<SortKey>("collected");
  const [open, setOpen] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api
      .listEvidence()
      .then(setList)
      .catch((exc: unknown) => setError(errorText(exc)));
    api
      .listCases()
      .then((c) => setCases(c.cases.map((x) => x.case)))
      .catch(() => setCases([])); // folders then come from the files alone
  }, []);
  useEffect(load, [load]);

  const rows: LibraryRow[] = useMemo(() => list?.items ?? [], [list]);
  const shown = useMemo(() => sortRows(filterRows(rows, filters), sort), [rows, filters, sort]);
  const folderList = useMemo(() => folders(rows, cases), [rows, cases]);
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const filtered = JSON.stringify({ ...filters, folder: ALL }) !== JSON.stringify({ ...NO_FILTERS });

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    const caseId = filters.folder !== ALL && filters.folder !== UNFILED ? filters.folder : undefined;
    try {
      const done = await api.uploadDocuments([...files], undefined, caseId);
      notify(`${done.length} file(s) added${caseId ? ` to ${caseId}` : ""}, each with its custody started.`, "success");
      load();
    } catch (exc) {
      notify(errorText(exc), "error");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className={`library ${open ? "with-drawer" : ""}`}>
      <nav className="library-folders" aria-label="Folders">
        <h2>Folders</h2>
        <ul>
          {folderList.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                className={filters.folder === f.id ? "on" : ""}
                aria-current={filters.folder === f.id}
                onClick={() => set({ folder: f.id })}
                title={f.id === ALL || f.id === UNFILED ? f.label : `${f.label} (${f.id})`}
              >
                <span className="library-folder-name">{f.label}</span>
                <span className="count">{f.count}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="library-note">A folder is a case. Open a file to file it under another.</p>
      </nav>

      <section className="library-main" aria-label="Files">
        <div className="library-head">
          <h2>
            {folderList.find((f) => f.id === filters.folder)?.label ?? "Files"}{" "}
            <span className="count">
              {shown.length === rows.length ? `${rows.length} file(s)` : `${shown.length} of ${rows.length}`}
            </span>
          </h2>
          <input ref={fileInput} type="file" multiple hidden onChange={(e) => void upload(e.target.files)} />
          <Button onClick={() => fileInput.current?.click()} disabled={uploading}>
            {uploading ? "Adding…" : "Add files"}
          </Button>
        </div>
        {list?.locker === "memory" ? (
          <Notice tone="warning">The database is not reachable: custody recorded now is lost when the engine restarts.</Notice>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}

        <div className="library-filters" role="search">
          <input
            type="search"
            placeholder="Search name, EV number, SHA-256, source…"
            value={filters.query}
            onChange={(e) => set({ query: e.target.value })}
            aria-label="Search files"
          />
          <select value={filters.kind} onChange={(e) => set({ kind: e.target.value })} aria-label="Kind">
            <option value="">Any kind</option>
            {kindsOf(rows).map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
          <select value={filters.integrity} onChange={(e) => set({ integrity: e.target.value as Filters["integrity"] })} aria-label="Integrity">
            <option value="">Any integrity</option>
            <option value="VERIFIED">Verified</option>
            <option value="UNCHECKED">Unchecked</option>
            <option value="FAILED">Failed</option>
          </select>
          <select value={filters.classification} onChange={(e) => set({ classification: e.target.value })} aria-label="Classification">
            <option value="">Any classification</option>
            {CLASSIFICATIONS.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <label className="library-check">
            <input type="checkbox" checked={filters.citedOnly} onChange={(e) => set({ citedOnly: e.target.checked })} /> Cited by a finding
          </label>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort">
            <option value="collected">Newest first</option>
            <option value="name">Name</option>
            <option value="size">Largest first</option>
            <option value="cited">Most cited</option>
          </select>
          {filtered ? (
            <button type="button" className="ui-button ghost sm" onClick={() => setFilters({ ...NO_FILTERS, folder: filters.folder })}>
              Clear filters
            </button>
          ) : null}
        </div>

        {!list && !error ? <p className="library-note">Loading the Library.</p> : null}
        {list && shown.length === 0 ? (
          <p className="library-note">{rows.length ? "No file matches these filters." : "No files yet. Add files, or attach them to a new investigation."}</p>
        ) : null}
        {shown.length ? (
          <table className="library-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Kind</th>
                <th>Size</th>
                <th>Integrity</th>
                <th>Classification</th>
                <th>Cited</th>
                <th>Collected</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(({ item, citations }) => (
                <tr
                  key={item.evidence_id}
                  className={open === item.evidence_id ? "on" : ""}
                  onClick={() => setOpen(item.evidence_id)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setOpen(item.evidence_id)}
                  tabIndex={0}
                  aria-selected={open === item.evidence_id}
                >
                  <td>
                    <div className="library-name">{item.name}</div>
                    <div className="library-sub mono">
                      {item.evidence_id}
                      {item.case_id ? ` · ${item.case_id}` : ""}
                    </div>
                  </td>
                  <td>{item.kind || "-"}</td>
                  <td className="nowrap">{sizeLabel(item.bytes)}</td>
                  <td>
                    <Badge tone={INTEGRITY_TONE[item.integrity] ?? "neutral"}>{item.integrity.toLowerCase()}</Badge>
                  </td>
                  <td>{item.classification.toLowerCase()}</td>
                  <td>{citations || "-"}</td>
                  <td className="nowrap">{new Date(item.collected_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      {open ? <CustodyDrawer key={open} evidenceId={open} cases={cases} onClose={() => setOpen("")} onChanged={load} /> : null}
    </div>
  );
}

function CustodyDrawer({
  evidenceId,
  cases,
  onClose,
  onChanged,
}: {
  evidenceId: string;
  cases: Case[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const notify = useToast();
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .getEvidence(evidenceId)
      .then(setDetail)
      .catch((exc: unknown) => setError(errorText(exc)));
  }, [evidenceId]);
  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const verify = async () => {
    setBusy(true);
    try {
      const check = await api.verifyEvidence(evidenceId);
      notify(check.integrity === "VERIFIED" ? "Integrity verified: the stored bytes match their SHA-256." : `Integrity ${check.integrity.toLowerCase()}.`, check.integrity === "VERIFIED" ? "success" : "error");
      load();
      onChanged();
    } catch (exc) {
      notify(errorText(exc), "error");
    } finally {
      setBusy(false);
    }
  };

  const file = async (caseId: string) => {
    setBusy(true);
    try {
      await api.updateEvidence(evidenceId, { case_id: caseId });
      notify(caseId ? `Filed under ${caseId}.` : "Taken out of its case.", "success");
      load();
      onChanged();
      casesChanged();
    } catch (exc) {
      notify(errorText(exc), "error");
    } finally {
      setBusy(false);
    }
  };

  const item = detail?.item;
  return (
    <aside className="library-drawer" aria-label="Custody">
      <div className="library-drawer-head">
        <h3>{item?.name ?? evidenceId}</h3>
        <button type="button" className="ui-button ghost sm" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {!item ? (
        !error ? <p className="library-note">Loading.</p> : null
      ) : (
        <>
          <dl className="library-facts">
            <dt>Evidence</dt>
            <dd className="mono">{item.evidence_id}</dd>
            <dt>SHA-256</dt>
            <dd className="mono library-hash">{item.sha256}</dd>
            <dt>Kind</dt>
            <dd>
              {[item.kind, sizeLabel(item.bytes), item.parser ? `read by ${item.parser}` : ""].filter(Boolean).join(" · ")}
            </dd>
            <dt>Collected</dt>
            <dd>
              {new Date(item.collected_at).toLocaleString()} by {item.collected_by}
            </dd>
            <dt>Source</dt>
            <dd>{item.source || "-"}</dd>
            <dt>Integrity</dt>
            <dd>
              <Badge tone={INTEGRITY_TONE[item.integrity] ?? "neutral"}>{item.integrity.toLowerCase()}</Badge>{" "}
              {item.integrity_checked_at
                ? `checked ${new Date(item.integrity_checked_at).toLocaleString()}`
                : item.integrity === "UNCHECKED"
                  ? "never checked"
                  : "on collection"}
            </dd>
          </dl>
          <div className="board-links">
            <Button size="sm" onClick={() => void verify()} disabled={busy}>
              Re-verify
            </Button>
            <a className="ui-button ghost sm" href={api.evidenceDownloadUrl(item.evidence_id)} download>
              Download original
            </a>
            <a className="ui-button ghost sm" href={evidenceLink(item.evidence_id)}>
              Full page
            </a>
          </div>

          <label className="library-file-under">
            <span>Filed under</span>
            <select value={item.case_id ?? ""} onChange={(e) => void file(e.target.value)} disabled={busy}>
              <option value="">Unfiled</option>
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.title || c.case_id} ({c.case_id})
                </option>
              ))}
              {item.case_id && !cases.some((c) => c.case_id === item.case_id) ? <option value={item.case_id}>{item.case_id}</option> : null}
            </select>
          </label>

          <h4>Cited by {detail.citations.length} finding(s)</h4>
          {detail.citations.length ? (
            <ul className="library-cites">
              {detail.citations.map((c) => (
                <li key={`${c.run_id}-${c.finding_id}-${c.locator}`}>
                  <a href={`#/mission/${c.run_id}`}>
                    {c.finding_id} · {c.locator}
                  </a>
                  <div className="library-sub">{c.claim}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="library-note">No finding rests on this file yet.</p>
          )}

          <h4>Chain of custody</h4>
          <ol className="library-custody">
            {detail.custody.map((e) => (
              <li key={e.event_id}>
                <span className="library-when">{new Date(e.at).toLocaleString()}</span>
                <strong>{custodyLabel(e.action)}</strong> by {e.actor}
                <div className="library-sub">{custodySummary(e.action, e.details)}</div>
              </li>
            ))}
          </ol>

          {detail.versions.length > 1 ? (
            <>
              <h4>Versions under this name</h4>
              <ul className="library-cites">
                {detail.versions.map((v) => (
                  <li key={v.evidence_id}>
                    <a href={evidenceLink(v.evidence_id)}>{v.evidence_id}</a> · {new Date(v.collected_at).toLocaleString()}
                    {v.evidence_id === item.evidence_id ? " (this one)" : ""}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}
    </aside>
  );
}
