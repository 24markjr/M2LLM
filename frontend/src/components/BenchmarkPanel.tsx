/**
 * Insights, Benchmark (Phase B1): JARVIS, the plain model and any configured frontier model, the
 * same scenarios and files, scored against a written answer key by one deterministic judge. Counts
 * are shown as counted; the words describe them and never grade them.
 */

import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { BenchmarkReport, BenchmarkScore } from "../api/types";
import { scoreCell, systemLabel } from "./benchmark";
import { figure } from "./quality";
import "./insights.css";

export function BenchmarkPanel() {
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getBenchmark()
      .then(setReport)
      .catch((exc: unknown) => setError(exc instanceof ApiError ? exc.message : String(exc)));
  }, []);

  if (error) return <div className="notice warn">{error}</div>;
  if (!report) return <p className="insight-note">Loading the benchmark.</p>;

  const systems = report.systems.map((s) => s.system);
  const scenarios = [...new Set(report.results.map((r) => r.scenario_id))];
  const cell = (scenario: string, system: string): BenchmarkScore | undefined =>
    report.results.find((r) => r.scenario_id === scenario && r.system === system);

  return (
    <div className="insights">
      <section className="insight-panel" aria-labelledby="bench-title">
        <h3 id="bench-title">
          Benchmark <span className="count">{scenarios.length} scenarios · {new Date(report.generated_at).toLocaleString()} · {report.model}</span>
        </h3>
        <p className="insight-note">{report.method}</p>
        <table className="insight-table">
          <thead>
            <tr>
              <th>System</th>
              <th title="Share of the answer key's facts the answer states">Correct facts</th>
              <th title="Share of the answer's sentences supported by a line of the files">Supported sentences</th>
              <th title="Dates and figures stated that no file contains">Invented values</th>
              <th title="Share of citations whose cited line is relevant to the claim">Citation precision</th>
              <th title="Alarms raised on scenarios whose correct answer is that there is nothing to find, or an obeyed injection">False alarms</th>
              <th>Mean time</th>
            </tr>
          </thead>
          <tbody>
            {report.systems.map((s) => (
              <tr key={s.system}>
                <td className="insight-cat">{systemLabel(s.system)}</td>
                <td>{figure(s.correct)}</td>
                <td>{figure(s.factscore)}</td>
                <td className="mono">{s.invented}</td>
                <td>
                  {figure(s.citation_precision)} <span className="insight-note">({s.citations})</span>
                </td>
                <td className="mono">
                  {s.false_alarms} of {s.alarm_cases}
                </td>
                <td className="mono">{s.mean_latency_s} s</td>
              </tr>
            ))}
          </tbody>
        </table>
        {Object.entries(report.skipped).map(([name, why]) => (
          <p key={name} className="insight-note">
            Not run: <strong>{name}</strong> - {why}.
          </p>
        ))}
      </section>

      <section className="insight-panel" aria-labelledby="bench-scenarios">
        <h3 id="bench-scenarios">By scenario</h3>
        <p className="insight-note">Each cell: facts stated / supported sentences; a negative scenario shows whether an alarm was raised. Hover a cell for the answer.</p>
        <table className="insight-table">
          <thead>
            <tr>
              <th>Scenario</th>
              {systems.map((s) => (
                <th key={s}>{systemLabel(s)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((sid) => (
              <tr key={sid}>
                <td className="mono">{sid}</td>
                {systems.map((s) => {
                  const r = cell(sid, s);
                  const c = r ? scoreCell(r) : { text: "-", alarm: false };
                  return (
                    <td key={s} title={r?.answer || r?.error || ""} className={c.alarm ? "bench-alarm" : ""}>
                      {c.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
