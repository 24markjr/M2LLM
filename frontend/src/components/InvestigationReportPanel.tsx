/**
 * The investigation report (Phase 51, designed in v4 Phase 5): built on demand from the run as it
 * stands - reviews and challenges included. "Open the report" shows the designed page; PDF and DOCX
 * are the same document. Each export is a numbered version signed with the report's content hash,
 * the run's receipt hash and a snapshot of the case, recorded in custody and the audit log.
 *
 * In an Indian language (v4 Phase 7): the page and the Word file, as a labelled machine translation
 * of the verified English report, which stays the master. The PDF is English only.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { InvestigationReport, LanguageInfo, ReportVersion } from "../api/types";
import { reportCounts } from "./investigationReport";

const FORMATS = ["pdf", "docx", "md", "json"] as const;

export function InvestigationReportPanel({ runId }: { runId?: string | undefined }) {
  const [report, setReport] = useState<InvestigationReport | null>(null);
  const [error, setError] = useState("");
  const [versions, setVersions] = useState<ReportVersion[]>([]);
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [language, setLanguage] = useState("");
  useEffect(() => {
    void api
      .languages()
      .then((c) => setLanguages(c.languages.filter((l) => l.code !== "en")))
      .catch(() => setLanguages([]));
  }, []);
  if (!runId) return null;
  const chosen = languages.find((l) => l.code === language);

  const build = () => {
    setError("");
    api
      .getInvestigationReport(runId)
      .then(setReport)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
    api
      .reportVersions(runId)
      .then(setVersions)
      .catch(() => setVersions([]));
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
              <a className="button primary" href={api.investigationReportUrl(runId, "html")} target="_blank" rel="noreferrer">
                Open the report
              </a>
              {FORMATS.map((fmt) => (
                <a className="button" key={fmt} href={api.investigationReportUrl(runId, fmt)}>
                  {fmt.toUpperCase()}
                </a>
              ))}
              <button onClick={build}>Rebuild</button>
            </div>
            {languages.length ? (
              <div className="row">
                <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Report language">
                  <option value="">In another language...</option>
                  {languages.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native} ({l.name})
                    </option>
                  ))}
                </select>
                {chosen ? (
                  <>
                    <a
                      className="button"
                      href={api.investigationReportUrl(runId, "html", chosen.code)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open in {chosen.name}
                    </a>
                    <a className="button" href={api.investigationReportUrl(runId, "docx", chosen.code)}>
                      DOCX in {chosen.name}
                    </a>
                    <span className="dim">A machine translation of the verified English; the PDF is English only.</span>
                  </>
                ) : null}
              </div>
            ) : null}
            <div className="dim mono">{report.content_hash}</div>
            {versions.length ? (
              <details>
                <summary className="dim">{versions.length} earlier export(s)</summary>
                <table className="metrics">
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Format</th>
                      <th>By</th>
                      <th>When</th>
                      <th>Case snapshot</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr key={v.version}>
                        <td>v{v.version}</td>
                        <td>{v.format}</td>
                        <td>{v.actor || "-"}</td>
                        <td>{new Date(v.exported_at).toLocaleString()}</td>
                        <td className="mono" title={`content ${v.content_hash}\nreceipt ${v.receipt_hash}`}>
                          {v.snapshot_hash.slice(0, 12)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ) : null}
          </>
        )}
        {error ? <div className="notice error">{error}</div> : null}
      </div>
    </div>
  );
}
