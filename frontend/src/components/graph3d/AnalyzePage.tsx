/**
 * Member 3's standalone use (Phase 32): pick documents, see their knowledge graph, no mission.
 *
 * Calls `POST /api/v1/knowledge/analyze`, which waits for extraction (one model call per chunk) and
 * stores nothing. Node details come from the graph itself, since there is no mission to ask.
 */

import { useState } from "react";

import { ApiError, api } from "../../api/client";
import type { AnalyzeResponse } from "../../api/types";
import KnowledgeExplorer from "./KnowledgeExplorer";

const FIXTURES = [
  "aurora_project_report.txt",
  "aurora_financial_report.txt",
  "aurora_budget.csv",
  "project_report.txt",
  "financial_report.txt",
  "milestone_report.txt",
  "budget.csv",
];

export default function AnalyzePage() {
  const [documents, setDocuments] = useState<string[]>(["aurora_project_report.txt", "aurora_financial_report.txt"]);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const run = () => {
    setBusy(true);
    setMessage("");
    setAnalysis(null);
    api
      .analyzeDocuments(documents)
      .then((result) => {
        setAnalysis(result);
        if (result.excluded.length) setMessage(`Not readable, left out: ${result.excluded.join(", ")}`);
      })
      .catch((exc: unknown) => setMessage(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc)))
      .finally(() => setBusy(false));
  };

  const toggle = (name: string) =>
    setDocuments((current) => (current.includes(name) ? current.filter((d) => d !== name) : [...current, name]));

  return (
    <>
      <div className="panel">
        <h2>Analyze documents</h2>
        <div className="panel-body">
          <div className="dim" style={{ marginBottom: 10 }}>
            Extract entities, relationships and claims, and the claims that conflict across sources, without
            running an investigation. Nothing is stored. Takes about ten seconds per document on a local model.
          </div>
          <div className="doc-picker">
            {FIXTURES.map((name) => (
              <label key={name}>
                <input type="checkbox" checked={documents.includes(name)} onChange={() => toggle(name)} />{" "}
                <span className="mono">{name}</span>
              </label>
            ))}
          </div>
          <div className="row">
            <button className="primary" disabled={busy || documents.length === 0} onClick={run}>
              {busy ? "Extracting." : "Analyze"}
            </button>
          </div>
        </div>
      </div>
      {message ? <div className="notice">{message}</div> : null}
      {analysis ? (
        <KnowledgeExplorer
          source={{ kind: "analysis", view: analysis.graph, snapshot: analysis.snapshot, timeline: analysis.timeline }}
        />
      ) : null}
    </>
  );
}
