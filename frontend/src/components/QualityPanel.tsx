/**
 * Insights, Quality (Phase 54, redesigned in U9): the quality figure as a headline with its
 * arithmetic, one card per component - each naming the report and the scenarios it comes from - the
 * agent-quality trend as a chart that breaks wherever the configuration changed, and the figures by
 * category. The raw metrics stay below, under Technical. Every number is read from a committed
 * report; nothing here is typed in.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { QualitySummary } from "../api/types";
import { figure, qualitySum, trendChart, type ChartPoint } from "./quality";
import "./insights.css";

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
  if (!summary) return <p className="insight-note">Loading the quality figures.</p>;

  return (
    <div className="insights">
      <section className="insight-hero" aria-labelledby="quality-title">
        <div>
          <h2 id="quality-title">Quality</h2>
          <div className="insight-big">{figure(summary.value)}</div>
          <p className="insight-note">{summary.formula}</p>
          <p className="mono insight-sum">{qualitySum(summary)}</p>
        </div>
        <Meter value={summary.value} large />
      </section>

      {summary.missing.map((m) => (
        <div className="notice warn" key={m}>
          {m}
        </div>
      ))}

      <section aria-label="Components">
        <div className="insight-cards">
          {summary.components.map((c) => (
            <article className="insight-card" key={c.name}>
              <header>
                <h3>{c.name}</h3>
                <span className="insight-value">{c.value.toFixed(3)}</span>
              </header>
              <Meter value={c.value} />
              <p className="insight-formula">{c.formula}</p>
              <p className="insight-note" title={c.dataset}>
                {c.dataset}
              </p>
              <p className="insight-source mono">{c.source}</p>
            </article>
          ))}
        </div>
      </section>

      <TrendChart summary={summary} />

      {summary.categories.length > 0 ? (
        <CategoryTable
          id="categories-title"
          title="By category"
          rows={summary.categories}
          note="A category of one or two scenarios is an anecdote, not a rate; hover a scenario count to see which."
        />
      ) : null}
      {summary.file_types?.length ? (
        <CategoryTable
          id="file-types-title"
          title="By kind of file"
          rows={summary.file_types}
          note={`The multimodal suite (${summary.file_types_source ?? ""}): each finding exists only inside the audio, video, scan or photo, so it is found only if that file was understood. Not part of the quality figure above.`}
        />
      ) : null}
    </div>
  );
}

function CategoryTable({ id, title, rows, note }: { id: string; title: string; rows: QualitySummary["categories"]; note: string }) {
  return (
    <section className="insight-panel" aria-labelledby={id}>
      <h3 id={id}>
        {title} <span className="count">{rows.length}</span>
      </h3>
      <table className="insight-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Verified</th>
            <th>Claims found</th>
            <th>Unsupported</th>
            <th>Negatives passed</th>
            <th>Scenarios</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.category}>
              <td className="insight-cat">{c.category.replace(/_/g, " ")}</td>
              <td>
                <Meter value={c.metrics.verification_success} label />
              </td>
              <td>{c.claims_found === null ? "-" : <Meter value={c.claims_found} label />}</td>
              <td className="mono">{c.metrics.unsupported_claim_rate.toFixed(3)}</td>
              <td className="mono">{figure(c.negative_passed)}</td>
              <td className="insight-scenarios" title={c.scenarios.join(", ")}>
                {c.scenarios.length}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="insight-note">{note}</p>
    </section>
  );
}

/** A 0-1 figure as a bar, with the number beside it when `label`. */
function Meter({ value, large, label }: { value: number | null; large?: boolean; label?: boolean }) {
  const v = value === null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <span className={`insight-meter-wrap ${large ? "large" : ""}`}>
      <span
        className="insight-meter"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value ?? undefined}
        aria-label={value === null ? "not measured" : value.toFixed(3)}
      >
        <span style={{ width: `${v * 100}%` }} />
      </span>
      {label ? <span className="mono">{figure(value)}</span> : null}
    </span>
  );
}

const W = 720;
const H = 220;
const PAD = { top: 14, right: 16, bottom: 28, left: 40 };

function TrendChart({ summary }: { summary: QualitySummary }) {
  const [hover, setHover] = useState<ChartPoint | null>(null);
  if (summary.trend.length === 0) return null;
  const { segments, breaks } = trendChart(summary, W, H, PAD);
  const all = segments.flat();
  const yAt = (v: number) => PAD.top + (1 - v) * (H - PAD.top - PAD.bottom);
  const firstAt = all[0]?.at ?? "";
  const lastAt = all.at(-1)?.at ?? "";
  const day = (at: string) => (at ? new Date(at).toLocaleDateString() : "");

  return (
    <section className="insight-panel" aria-labelledby="trend-title">
      <h3 id="trend-title">
        Agent quality over time <span className="count">{summary.trend.length} reports</span>
      </h3>
      <p className="insight-note">
        {summary.agent_formula.replace(/\.?$/, ".")} The line breaks wherever the model, prompts or configuration changed: figures on either side of a
        break describe different systems and are not joined.
      </p>
      <div className="insight-chart">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Agent quality across ${summary.trend.length} reports, ${segments.length} configurations`}>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={yAt(t)} y2={yAt(t)} />
              <text className="tick" x={PAD.left - 6} y={yAt(t) + 4} textAnchor="end">
                {t.toFixed(2)}
              </text>
            </g>
          ))}
          {breaks.map((x) => (
            <line key={x} className="break" x1={x} x2={x} y1={PAD.top} y2={H - PAD.bottom}>
              <title>configuration changed</title>
            </line>
          ))}
          {segments.map((s, i) => (
            <polyline key={i} className="series" points={s.map((p) => `${p.x},${p.y}`).join(" ")} />
          ))}
          {all.map((p) => (
            <g key={p.report} onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(p)} onBlur={() => setHover(null)} tabIndex={0}>
              <circle className="hit" cx={p.x} cy={p.y} r={12} />
              <circle className={`dot ${hover?.report === p.report ? "on" : ""}`} cx={p.x} cy={p.y} r={4} />
            </g>
          ))}
          <text className="tick" x={PAD.left} y={H - 8}>
            {day(firstAt)}
          </text>
          <text className="tick" x={W - PAD.right} y={H - 8} textAnchor="end">
            {day(lastAt)}
          </text>
        </svg>
        {hover ? (
          <div className="insight-tip" style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%` }} role="status">
            <strong>{hover.value.toFixed(3)}</strong>
            <span>{new Date(hover.at).toLocaleString()}</span>
            <span className="mono">{hover.report}</span>
          </div>
        ) : null}
      </div>
      <details className="insight-details">
        <summary>The figures as a table</summary>
        <table className="insight-table">
          <thead>
            <tr>
              <th>Report</th>
              <th>Agent quality</th>
              <th>Configuration</th>
            </tr>
          </thead>
          <tbody>
            {summary.trend.map((p, i) => (
              <tr key={p.report}>
                <td className="mono">{p.report}</td>
                <td className="mono">{p.agent_quality.toFixed(3)}</td>
                <td>{i > 0 && summary.trend[i - 1]?.comparable_key !== p.comparable_key ? "changed" : i === 0 ? "first" : "same"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
