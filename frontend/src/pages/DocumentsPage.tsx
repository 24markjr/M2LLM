/**
 * Documents and workspaces (Phase 40): Member 2's ingest and semantic search, for people.
 *
 * A workspace is a named set of documents whose passages are chunked, embedded and stored. Here a
 * person sees what each workspace holds (parser, hash, chunks), adds files to it, and searches it
 * by meaning. Every hit is a citation and leads on: investigate that file, or the whole workspace,
 * in a new mission that searches the same workspace.
 */

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { RetrieveResponse, WorkspaceView } from "../api/types";
import {
  DEFAULT_WORKSPACE,
  documentsLink,
  newMissionLink,
  objectiveFromSearch,
  scoreLabel,
  shortHash,
  validWorkspace,
} from "../components/workspaces";

export function DocumentsPage({ workspace = DEFAULT_WORKSPACE }: { workspace?: string }) {
  const [names, setNames] = useState<string[]>([DEFAULT_WORKSPACE]);
  const [view, setView] = useState<WorkspaceView | null>(null);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api.listWorkspaces().then(setNames).catch(() => setNames([DEFAULT_WORKSPACE]));
    api
      .getWorkspace(workspace)
      .then(setView)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, [workspace]);

  useEffect(refresh, [refresh]);

  const upload = (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    api
      .uploadDocuments(Array.from(files), workspace)
      .then((results) => {
        const failed = results.filter((r) => r.has_text && !r.ingested);
        if (failed.length) {
          setError(`Stored but not searchable yet: ${failed.map((r) => `${r.name} (${r.note})`).join(", ")}`);
        }
        refresh();
      })
      .catch((exc: unknown) => setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc)))
      .finally(() => setBusy(false));
  };

  const documents = view?.documents ?? [];
  const all = documents.map((d) => d.document_id);

  return (
    <>
      <div className="panel">
        <h2>
          Documents <span className="count">{view ? `store: ${view.store}` : ""}</span>
        </h2>
        <div className="panel-body">
          <div className="dim">
            Each workspace keeps its documents chunked and embedded, so they can be searched by meaning, not
            only by the words in them. Every passage found is a citation. A mission that names a workspace
            searches it the same way.
            {view?.store === "memory" ? " The database is not reachable: this workspace lives in memory and is lost on restart." : ""}
          </div>
          <div className="row" style={{ marginTop: 12, flexWrap: "wrap", gap: 8 }}>
            {names.map((name) => (
              <a key={name} className={`button ${name === workspace ? "primary" : ""}`} href={documentsLink(name)}>
                {name}
              </a>
            ))}
            <span className="spacer" />
            <input
              aria-label="New workspace name"
              placeholder="new workspace"
              value={newName}
              onChange={(e) => setNewName(e.target.value.trim())}
              style={{ width: 160 }}
            />
            <a
              className="button"
              aria-disabled={!validWorkspace(newName)}
              href={validWorkspace(newName) ? documentsLink(newName) : undefined}
              title="Letters, digits, - and _. It exists once a file is added to it."
            >
              Open
            </a>
          </div>
        </div>
      </div>

      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>
          {workspace} <span className="count">{documents.length} document(s)</span>
        </h2>
        <div className="panel-body">
          <div className="row" style={{ marginBottom: 10 }}>
            <label className="button">
              {busy ? "Adding." : "Add files"}
              <input type="file" multiple hidden disabled={busy} onChange={(e) => upload(e.target.files)} />
            </label>
            {documents.length ? (
              <a className="button" href={newMissionLink({ documents: all, workspace })}>
                Investigate this workspace
              </a>
            ) : null}
          </div>
          {documents.length ? (
            <div className="table-scroll">
            <table className="metrics">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Kind</th>
                  <th>Parser</th>
                  <th>Chunks</th>
                  <th>SHA-256</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.document_id}>
                    <td className="mono">{d.document_id}</td>
                    <td>{d.kind}</td>
                    <td className="mono dim">{d.parser || "-"}</td>
                    <td title={`cut by the ${d.chunker} chunker`}>{d.chunks}</td>
                    <td className="mono dim" title={d.sha256}>
                      {shortHash(d.sha256)}
                    </td>
                    <td>
                      <a href={newMissionLink({ documents: [d.document_id], workspace })}>investigate</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : (
            <div className="empty">
              Nothing in this workspace yet. Add files here, or attach them to a mission that names it.
            </div>
          )}
        </div>
      </div>

      {documents.length ? <PassageSearch workspace={workspace} /> : null}
    </>
  );
}

function PassageSearch({ workspace }: { workspace: string }) {
  const [query, setQuery] = useState("");
  // 0 by measurement (Experiment 006): a query nothing answers scored 0.80, above the first relevant
  // hit of a third of answerable queries, so no threshold separates them. Scores are shown instead.
  const [minScore, setMinScore] = useState(0);
  const [result, setResult] = useState<RetrieveResponse | null>(null);
  const [error, setError] = useState("");

  const search = (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setError("");
    api
      .retrieveContext({ workspace_id: workspace, query: query.trim(), k: 10, min_score: minScore })
      .then(setResult)
      .catch((exc: unknown) => setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc)));
  };

  return (
    <div className="panel">
      <h2>
        Search by meaning{" "}
        {result ? <span className="count">{`${result.hits.length} passage(s) · ${result.store}`}</span> : null}
      </h2>
      <div className="panel-body">
        <form className="row" onSubmit={search}>
          <input
            aria-label="What to look for"
            placeholder="e.g. spending above what was approved"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <label className="dim mono" title="Cosine similarity mapped to 0-1. Experiment 006 found no threshold that drops non-answers without dropping answers: judge by the passage, not the number.">
            min score{" "}
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              style={{ width: 70 }}
            />
          </label>
          <button className="primary" type="submit" disabled={!query.trim()}>
            Search
          </button>
        </form>
        {error ? <div className="notice error">{error}</div> : null}
        {result && !result.hits.length ? <div className="empty">No passage scored above {minScore}.</div> : null}
        {result?.hits.map((hit) => (
          <div key={hit.source} className="passage">
            <div className="row">
              <span className="mono">{hit.source}</span>
              <span className="dim mono">score {scoreLabel(hit.score)}</span>
              <span className="spacer" />
              <a
                href={newMissionLink({
                  documents: [hit.document_id],
                  workspace,
                  objective: objectiveFromSearch(query),
                })}
              >
                investigate this file
              </a>
            </div>
            <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>
              {hit.text}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
