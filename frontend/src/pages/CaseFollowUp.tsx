/**
 * A case after its investigations (v4 Phase 3b): findings that evidence added later was not read
 * for, and two runs of the case compared finding by finding.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { CaseInvestigation, RunComparison, StaleFinding } from "../api/types";
import { Notice } from "../ui/components";

export function StaleNotice({ caseId }: { caseId: string }) {
  const [stale, setStale] = useState<StaleFinding[]>([]);
  useEffect(() => {
    api
      .staleFindings(caseId)
      .then(setStale)
      .catch(() => setStale([]));
  }, [caseId]);
  if (!stale.length) return null;
  const files = [...new Set(stale.flatMap((s) => s.newer_evidence))];
  return (
    <Notice tone="warning">
      {stale.length} finding(s) were checked before {files.join(", ")} {files.length === 1 ? "was" : "were"} added to this
      case. Ask below to re-check them: "recheck {stale.map((s) => s.finding_id).slice(0, 3).join(", ")}".
    </Notice>
  );
}

export function CompareRuns({ caseId, investigations }: { caseId: string; investigations: CaseInvestigation[] }) {
  const runs = investigations.map((i) => i.run_id);
  const [a, setA] = useState(runs[1] ?? "");
  const [b, setB] = useState(runs[0] ?? "");
  const [result, setResult] = useState<RunComparison | null>(null);
  if (runs.length < 2) return null;

  const compare = () => {
    void api
      .compareRuns(caseId, a, b)
      .then(setResult)
      .catch(() => setResult(null));
  };
  const label = (run: string) => investigations.find((i) => i.run_id === run)?.objective.slice(0, 60) ?? run;

  return (
    <div className="panel">
      <h2>Compare two investigations</h2>
      <div className="panel-body">
        <div className="row">
          <select value={a} onChange={(e) => setA(e.target.value)} aria-label="First investigation">
            {runs.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
          <span>with</span>
          <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Second investigation">
            {runs.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
          <button onClick={compare} disabled={a === b}>
            Compare
          </button>
        </div>
        {result ? (
          <table className="metrics" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>First</th>
                <th>Second</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {result.pairs.map((p, i) => (
                <tr key={i}>
                  <td>{p.a ? `${p.a} ${p.status_a.toLowerCase()}: ${p.claim_a}` : "-"}</td>
                  <td>{p.b ? `${p.b} ${p.status_b.toLowerCase()}: ${p.claim_b}` : "-"}</td>
                  <td>
                    <strong>{p.change}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
