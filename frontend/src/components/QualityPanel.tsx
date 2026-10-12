/**
 * Evaluation v2 (Phase 54): one quality figure with its formula and every component shown - each
 * naming the report and the scenarios or cases it comes from - the figures by category, and the
 * agent-quality trend. The raw metrics stay below, under Technical.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { QualitySummary } from "../api/types";
import { figure, qualitySum, trendSegments } from "./quality";

export function QualityPanel() {
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getQuality()
      .then(setSummary)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, []);

  if (error) return <div className="notice error">{error}</div>;
  if (!summary) return null;

  return (
    <>
      <div className="panel">
        <h2>
          Quality <span className="count">{figure(summary.value)}</span>
        </h2>
        <div className="panel-body">
          <div className="hint">{summary.formula}</div>
          <div className="mono why-sum">{qualitySum(summary)}</div>
          <table className="metrics">
            <thead>
              <tr>
                <th>Component</th>
                <th>Value</th>
                <th>Formula</th>
                <th>Measured on</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {summary.components.map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td className="mono">{c.value.toFixed(3)}</td>
                  <td className="dim">{c.formula}</td>
                  <td className="dim">{c.dataset}</td>
                  <td className="mono dim">{c.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {summary.missing.map((m) => (
            <div className="notice warn" key={m}>
              Not counted: {m}
            </div>
          ))}
          <div className="dim">
            Trend ({summary.agent_formula}):{" "}
            {trendSegments(summary)
              .map((s) => s.values.map((v) => v.toFixed(3)).join(" → "))
              .join(" | configuration changed | ")}
          </div>
        </div>
      </div>

      {summary.categories.length ? (
        <div className="panel">
          <h2>
            By category <span className="count">{summary.categories.length} categories</span>
          </h2>
          <div className="panel-body">
            <table className="metrics">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Scenarios</th>
                  <th>Unsupported</th>
                  <th>Verified</th>
                  <th>Negatives passed</th>
                  <th>Claims found</th>
                </tr>
              </thead>
              <tbody>
                {summary.categories.map((c) => (
                  <tr key={c.category}>
                    <td>{c.category.replace(/_/g, " ")}</td>
                    <td className="dim">{c.scenarios.join(", ")}</td>
                    <td className="mono">{c.metrics.unsupported_claim_rate.toFixed(3)}</td>
                    <td className="mono">{c.metrics.verification_success.toFixed(3)}</td>
                    <td className="mono">{figure(c.negative_passed)}</td>
                    <td className="mono">{figure(c.claims_found)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="dim">A category of one or two scenarios is an anecdote, not a rate.</div>
          </div>
        </div>
      ) : null}
    </>
  );
}
