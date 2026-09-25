/**
 * The evaluation dashboard.
 *
 * Charts are inline SVG rather than a charting library. What is drawn here is a handful of
 * points per metric, and the two rules that matter are not things a library would enforce:
 *
 * **Points are only joined within a comparability key.** Two reports produced with different
 * models or prompt versions describe different systems. A line drawn between them shows a
 * regression or an improvement that never happened, which is exactly the lie the backend's
 * regression check refuses to tell. The series breaks at every key change and says so.
 *
 * **Direction comes from the API.** Whether higher is better is a property of the metric. A
 * frontend holding its own copy would eventually colour a rising `unsupported_claim_rate` green.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { MetricDirections, MetricPoint } from "../api/types";

/** The metrics worth a chart each. The rest are in the table. */
const CHARTED = [
  "unsupported_claim_rate",
  "plan_validity",
  "task_efficiency",
  "intent_accuracy",
  "verification_success",
  "replanning_success",
];

export function EvaluationDashboard() {
  const [points, setPoints] = useState<MetricPoint[]>([]);
  const [directions, setDirections] = useState<MetricDirections>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.listEvalReports(), api.getMetricDirections()])
      .then(([rows, dirs]) => {
        setPoints(rows);
        setDirections(dirs);
        setError("");
      })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="panel">
        <div className="empty">Loading evaluation reports.</div>
      </div>
    );
  }

  if (error) return <div className="notice error">{error}</div>;

  if (points.length === 0) {
    return (
      <div className="panel">
        <h2>Evaluation</h2>
        <div className="empty">
          No reports yet. Run <code className="mono">python -m app.cli eval --suite all</code>.
        </div>
      </div>
    );
  }

  const latest = points[points.length - 1];
  const keys = new Set(points.map((p) => p.comparable_key));

  return (
    <>
      {keys.size > 1 ? (
        <div className="notice warn">
          These {points.length} reports span <strong>{keys.size} different configurations</strong>{" "}
          (model, prompt versions or config). Series below break wherever the configuration
          changed, because numbers either side of a break describe different systems and joining
          them would show a change that never happened.
        </div>
      ) : null}

      {latest ? <LatestRun point={latest} /> : null}

      <div className="panel">
        <h2>
          Trends
          <span className="count">{points.length} committed reports</span>
        </h2>
        <div className="chart-grid">
          {CHARTED.map((metric) => (
            <Trend
              key={metric}
              metric={metric}
              points={points}
              direction={directions[metric] ?? "higher"}
            />
          ))}
        </div>
      </div>

      <RunTable points={points} directions={directions} />
    </>
  );
}

function LatestRun({ point }: { point: MetricPoint }) {
  const failing = point.confabulations > 0 || point.blind_spots > 0;

  return (
    <>
      {failing ? (
        <div className="notice error">
          <strong>Thresholds failed.</strong>{" "}
          {point.confabulations > 0
            ? `${point.confabulations} negative case(s) produced findings where none should exist. `
            : ""}
          {point.blind_spots > 0
            ? `${point.blind_spots} positive case(s) produced no findings at all. `
            : ""}
          Neither is expressible as a metric, which is why both are checked separately.
        </div>
      ) : null}

      <div className="panel">
        <h2>
          Latest run
          <span className="count">
            {point.model} &middot; {new Date(point.generated_at).toLocaleString()} &middot; suite{" "}
            {point.suite}
          </span>
        </h2>
        <div className="panel-body">
          <div className="hint mono">
            prompts:{" "}
            {Object.entries(point.prompt_versions)
              .map(([role, version]) => `${role}=v${version}`)
              .join(", ") || "(none recorded)"}{" "}
            &middot; config: {point.config_hash}
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * One metric over time, as a broken-series sparkline.
 *
 * A gap in the line is meaningful: it marks a point where the configuration changed and the two
 * sides are not comparable.
 */
function Trend({
  metric,
  points,
  direction,
}: {
  metric: string;
  points: MetricPoint[];
  direction: "higher" | "lower";
}) {
  const values = points.map((p) => p.metrics[metric] ?? 0);
  const max = Math.max(...values, direction === "higher" ? 1 : 0.001);
  const min = Math.min(...values, 0);
  const span = max - min || 1;

  const width = 260;
  const height = 74;
  const pad = 6;

  const x = (index: number) =>
    points.length === 1
      ? width / 2
      : pad + (index / (points.length - 1)) * (width - pad * 2);
  const y = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2);

  // Split into runs of comparable points. A break is drawn as a break.
  const segments: { index: number; value: number }[][] = [];
  let current: { index: number; value: number }[] = [];
  points.forEach((point, index) => {
    const previous = index > 0 ? points[index - 1] : undefined;
    if (previous && previous.comparable_key !== point.comparable_key) {
      if (current.length > 0) segments.push(current);
      current = [];
    }
    current.push({ index, value: values[index] ?? 0 });
  });
  if (current.length > 0) segments.push(current);

  const last = values[values.length - 1] ?? 0;
  const first = values[0] ?? 0;
  const movement = last - first;
  const improved = direction === "lower" ? movement < 0 : movement > 0;

  return (
    <div className="chart">
      <div className="chart-head">
        <span className="chart-title">{metric}</span>
        <span className="chart-dir">{direction} is better</span>
      </div>
      <svg width={width} height={height} role="img" aria-label={`${metric} over time`}>
        {segments.map((segment, segmentIndex) => (
          <g key={segmentIndex}>
            {segment.length > 1 ? (
              <polyline
                className="spark"
                points={segment.map((p) => `${x(p.index)},${y(p.value)}`).join(" ")}
              />
            ) : null}
            {segment.map((p) => (
              <circle key={p.index} className="spark-dot" cx={x(p.index)} cy={y(p.value)} r={3} />
            ))}
          </g>
        ))}
      </svg>
      <div className="chart-foot">
        <span className="chart-value">{format(metric, last)}</span>
        {points.length > 1 ? (
          <span className={improved ? "delta good" : movement === 0 ? "delta" : "delta bad"}>
            {movement === 0
              ? "no change"
              : `${movement > 0 ? "+" : ""}${format(metric, movement)} since first`}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function RunTable({
  points,
  directions,
}: {
  points: MetricPoint[];
  directions: MetricDirections;
}) {
  const metrics = Object.keys(directions);

  return (
    <div className="panel">
      <h2>
        Every report
        <span className="count">newest last</span>
      </h2>
      <div className="table-scroll">
        <table className="metrics">
          <thead>
            <tr>
              <th>when</th>
              <th>model</th>
              <th>suite</th>
              {metrics.map((metric) => (
                <th key={metric} title={`${directions[metric]} is better`}>
                  {metric.replace(/_/g, " ")}
                </th>
              ))}
              <th>confab</th>
              <th>blind</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={index}>
                <td className="mono">{point.generated_at.slice(0, 16).replace("T", " ")}</td>
                <td className="mono">{point.model}</td>
                <td className="mono">{point.suite}</td>
                {metrics.map((metric) => (
                  <td key={metric} className="mono num">
                    {format(metric, point.metrics[metric] ?? 0)}
                  </td>
                ))}
                <td className={point.confabulations > 0 ? "mono num bad-cell" : "mono num"}>
                  {point.confabulations}
                </td>
                <td className={point.blind_spots > 0 ? "mono num bad-cell" : "mono num"}>
                  {point.blind_spots}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function format(metric: string, value: number): string {
  if (metric === "latency_s") return `${value.toFixed(1)}s`;
  if (metric === "task_efficiency") return `${value.toFixed(2)}x`;
  return value.toFixed(3);
}
