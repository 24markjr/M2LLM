/**
 * The investigation report (Phase 51): built on demand from the run as it stands - reviews and
 * challenges included - with its risk, executive summary, what awaits review, recommendations, and
 * exports as Markdown, PDF, DOCX and JSON. Each export is recorded in the custody of every cited
 * document and in the audit log; the content hash identifies the copy.
 */

import { useState } from "react";

import { api } from "../api/client";
import type { InvestigationReport } from "../api/types";
import { reportCounts } from "./investigationReport";

const FORMATS = ["pdf", "docx", "md", "json"] as const;

export function InvestigationReportPanel({ runId }: { runId?: string | undefined }) {
  const [report, setReport] = useState<InvestigationReport | null>(null);
  const [error, setError] = useState("");
  if (!runId) return null;

  const build = () => {
    setError("");
    api
      .getInvestigationReport(runId)
      .then(setReport)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  return (
    <div className="panel">
      <h2>
        Investigation report
        {report ? <span className={`badge risk ${report.risk.toLowerCase()}`}>risk {report.risk}</span> : null}
      </h2>
      <div className="panel-body">
        {!report ? (
          <button onClick={build}>Build the report</button>
        ) : (
          <>
            <div className="hint">
              {report.risk_reason} · {reportCounts(report)}
            </div>
            <div className="why-head">Executive summary</div>
            <ul>
              {report.executive_summary.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {report.recommendations.length ? (
              <>
                <div className="why-head">Recommendations</div>
                <ul>
                  {report.recommendations.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </>
            ) : null}
            <div className="row">
              {FORMATS.map((fmt) => (
                <a className="button" key={fmt} href={api.investigationReportUrl(runId, fmt)}>
                  {fmt.toUpperCase()}
                </a>
              ))}
              <button onClick={build}>Rebuild</button>
            </div>
            <div className="dim mono">{report.content_hash}</div>
          </>
        )}
        {error ? <div className="notice error">{error}</div> : null}
      </div>
    </div>
  );
}
