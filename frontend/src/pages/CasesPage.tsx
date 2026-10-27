/**
 * Cases (Phase 44): the home page. A case is the matter the investigations are about - its evidence,
 * its investigations and (later) its reviews and reports - under one number a person can quote.
 *
 * The list opens cases and shows what each holds; a case's page is where everything about the matter
 * starts: a new investigation inside it, files added to its evidence, its investigations and the
 * evidence they read, each a link to the mission or the Evidence Locker.
 */

import { casesChanged } from "../shell/Sidebar";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { CaseCounters, CaseDetail, CaseList, CaseSeverity, CaseStatus } from "../api/types";
import { CASE_STATUSES, SEVERITIES, caseLink } from "../components/cases";
import { evidenceLink } from "../components/evidence";
import { newMissionLink, shortHash } from "../components/workspaces";
import { ConversationPanel } from "./Conversation";

function errorText(exc: unknown): string {
  return exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc);
}

function StoreNote({ store }: { store: string }) {
  return store === "memory" ? (
    <div className="notice warn">
      The database is not reachable: cases are held in memory and lost when the engine restarts. Start it
      with <code>docker compose up -d postgres</code>.
    </div>
  ) : null;
}

function Counters({ counters }: { counters: CaseCounters }) {
  const parts = [
    `${counters.investigations} investigation(s)${counters.running ? ` (${counters.running} running)` : ""}`,
    `${counters.evidence} evidence item(s)`,
    `${counters.findings} finding(s), ${counters.verified} verified`,
    counters.contradictions ? `${counters.contradictions} contradiction(s)` : "",
    counters.open_gaps ? `${counters.open_gaps} open gap(s)` : "",
  ].filter(Boolean);
  return (
    <span className="dim">
      {parts.join(" · ")}
      {counters.failed_integrity ? (
        <span className="integrity failed"> · {counters.failed_integrity} failed integrity</span>
      ) : null}
    </span>
  );
}

export function CasesPage() {
  const [list, setList] = useState<CaseList | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<CaseSeverity>("MEDIUM");
  const [description, setDescription] = useState("");

  const load = useCallback(() => {
    api
      .listCases()
      .then(setList)
      .catch((exc: unknown) => setError(errorText(exc)));
  }, []);

  useEffect(load, [load]);

  const open = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim().length < 3) return;
    api
      .openCase({ title: title.trim(), description: description.trim(), severity })
      .then((created) => {
        casesChanged(); // the sidebar lists it at once (U3)
        window.location.hash = caseLink(created.case_id);
      })
      .catch((exc: unknown) => setError(errorText(exc)));
  };

  return (
    <>
      <div className="panel">
        <h2>Open a case</h2>
        <div className="panel-body">
          <form onSubmit={open}>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <input
                aria-label="Case title"
                placeholder="What is the matter? e.g. Helix budget overrun"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                style={{ flex: 1, minWidth: 240 }}
              />
              <select aria-label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value as CaseSeverity)}>
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <button className="primary" type="submit" disabled={title.trim().length < 3}>
                Open case
              </button>
            </div>
            <textarea
              aria-label="Description"
              rows={2}
              placeholder="Background (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ marginTop: 8, width: "100%" }}
            />
          </form>
          <div className="hint">
            A case holds the evidence and every investigation run over it. Investigations outside any case are
            listed under <a href="#/missions">All investigations</a>.
          </div>
        </div>
      </div>
      {list ? <StoreNote store={list.store} /> : null}
      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>
          Cases <span className="count">{list ? list.cases.length : ""}</span>
        </h2>
        <div className="panel-body">
          {list && !list.cases.length ? <div className="empty">No cases yet. Open one above.</div> : null}
          {list?.cases.map(({ case: c, counters }) => (
            <a key={c.case_id} className="case-row" href={caseLink(c.case_id)}>
              <div className="row">
                <span className="mono">{c.case_id}</span>
                <strong>{c.title}</strong>
                <span className="spacer" />
                <span className={`severity ${c.severity.toLowerCase()}`}>{c.severity}</span>
                <span className="badge">{c.status}</span>
              </div>
              <Counters counters={counters} />
            </a>
          ))}
        </div>
      </div>
    </>
  );
}

export function CasePage({ caseId }: { caseId: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api
      .getCase(caseId)
      .then(setDetail)
      .catch((exc: unknown) => setError(errorText(exc)));
  }, [caseId]);

  useEffect(load, [load]);

  // Refresh while an investigation is running, so the counters follow it. Stops by itself.
  useEffect(() => {
    if (!detail?.counters.running) return undefined;
    const timer = window.setTimeout(load, 5000);
    return () => window.clearTimeout(timer);
  }, [detail, load]);

  const change = (body: { status?: CaseStatus; severity?: CaseSeverity }) => {
    api
      .updateCase(caseId, body)
      .then(() => {
        casesChanged();
        load();
      })
      .catch((exc: unknown) => setError(errorText(exc)));
  };

  const addFiles = (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    api
      .uploadDocuments(Array.from(files), undefined, caseId)
      .then(load)
      .catch((exc: unknown) => setError(errorText(exc)))
      .finally(() => setBusy(false));
  };

  if (error && !detail) return <div className="notice error">{error}</div>;
  if (!detail) return <div className="empty">Loading {caseId}.</div>;
  const { case: c, counters } = detail;
  const closed = c.status === "CLOSED";
  const documents = detail.evidence.map((e) => e.item.name);

  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <a className="button" href="#/cases">
          &larr; Cases
        </a>
        <span className="spacer" />
        {!closed ? (
          <a className="button primary" href={newMissionLink({ caseId, documents })}>
            New investigation in this case
          </a>
        ) : null}
      </div>
      <StoreNote store={detail.store} />
      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>
          {c.case_id} <span className="count">{c.title}</span>
        </h2>
        <div className="panel-body">
          {c.description ? <p>{c.description}</p> : null}
          <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
            <label className="dim">
              Status{" "}
              <select aria-label="Status" value={c.status} onChange={(e) => change({ status: e.target.value as CaseStatus })}>
                {CASE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="dim">
              Severity{" "}
              <select
                aria-label="Severity"
                value={c.severity}
                onChange={(e) => change({ severity: e.target.value as CaseSeverity })}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <span className="dim">
              Owner {c.owner} · opened {new Date(c.opened_at).toLocaleString()}
              {c.closed_at ? ` · closed ${new Date(c.closed_at).toLocaleString()}` : ""}
            </span>
          </div>
          <div style={{ marginTop: 10 }}>
            <Counters counters={counters} />
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>
          Investigations <span className="count">{detail.investigations.length}</span>
        </h2>
        <div className="panel-body">
          {detail.investigations.length ? (
            detail.investigations.map((i) => (
              <a key={i.run_id} className="case-row" href={`#/mission/${i.run_id}`}>
                <div className="row">
                  <span>{i.objective}</span>
                  <span className="spacer" />
                  <span className="badge">{i.status}</span>
                </div>
                <span className="dim">
                  {i.findings} finding(s), {i.verified} verified
                  {i.contradictions ? ` · ${i.contradictions} contradiction(s)` : ""}
                  {i.open_gaps ? ` · ${i.open_gaps} open gap(s)` : ""} · {new Date(i.created_at).toLocaleString()}
                </span>
              </a>
            ))
          ) : (
            <div className="empty">
              No investigation yet.{" "}
              {!closed ? <a href={newMissionLink({ caseId, documents })}>Start one</a> : null}
            </div>
          )}
        </div>
      </div>

      <ConversationPanel caseId={caseId} closed={closed} />

      <div className="panel">
        <h2>
          Evidence <span className="count">{detail.evidence.length} item(s)</span>
        </h2>
        <div className="panel-body">
          <div className="row" style={{ marginBottom: 10 }}>
            <button onClick={() => fileInput.current?.click()} disabled={busy || closed}>
              {busy ? "Adding." : "Add files to this case"}
            </button>
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => addFiles(e.target.files)} />
            <a href="#/evidence">Evidence Locker</a>
          </div>
          {detail.evidence.length ? (
            <div className="table-scroll">
              <table className="metrics">
                <thead>
                  <tr>
                    <th>Evidence</th>
                    <th>Name</th>
                    <th>SHA-256</th>
                    <th>Integrity</th>
                    <th>Filed</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.evidence.map(({ item, added_at, added_by }) => (
                    <tr key={item.evidence_id}>
                      <td>
                        <a className="mono" href={evidenceLink(item.evidence_id)}>
                          {item.evidence_id}
                        </a>
                      </td>
                      <td className="mono">{item.name}</td>
                      <td className="mono dim" title={item.sha256}>
                        {shortHash(item.sha256)}
                      </td>
                      <td>
                        <span className={`integrity ${item.integrity.toLowerCase()}`}>{item.integrity}</span>
                      </td>
                      <td className="dim">
                        {new Date(added_at).toLocaleString()} · {added_by}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">No evidence filed yet.</div>
          )}
        </div>
      </div>
    </>
  );
}
