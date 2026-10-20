/** The quality summary as the console shows it (Phase 54). Pure, so it is tested. */

import type { QualitySummary } from "../api/types";

/** "0.93", or "-" when there is nothing to compute it from. */
export function figure(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : value.toFixed(3);
}

/** The arithmetic laid out: "mean(1.000, 0.976, ...) = 0.927". */
export function qualitySum(summary: QualitySummary): string {
  if (summary.value === null || summary.components.length === 0) return "";
  const terms = summary.components.map((c) => c.value.toFixed(3)).join(", ");
  return `mean(${terms}) = ${summary.value.toFixed(3)}`;
}

/** Trend points joined only within one configuration (the same rule the metric charts keep). */
export function trendSegments(summary: QualitySummary): { key: string; values: number[] }[] {
  const segments: { key: string; values: number[] }[] = [];
  for (const point of summary.trend) {
    const last = segments[segments.length - 1];
    if (last && last.key === point.comparable_key) last.values.push(point.agent_quality);
    else segments.push({ key: point.comparable_key, values: [point.agent_quality] });
  }
  return segments;
}

export interface ChartPoint {
  x: number;
  y: number;
  value: number;
  at: string;
  report: string;
}

/**
 * The agent-quality trend laid out for an SVG line chart (U9): one x step per report, y from 0 to 1,
 * points joined only within one configuration, and a break wherever the configuration changed -
 * a line across a change would show an improvement or a regression that never happened.
 */
export function trendChart(
  summary: QualitySummary,
  width: number,
  height: number,
  pad = { top: 12, right: 12, bottom: 24, left: 36 },
): { segments: ChartPoint[][]; breaks: number[] } {
  const n = summary.trend.length;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => pad.top + (1 - Math.max(0, Math.min(1, v))) * plotH;
  const segments: ChartPoint[][] = [];
  const breaks: number[] = [];
  summary.trend.forEach((p, i) => {
    const point = { x: x(i), y: y(p.agent_quality), value: p.agent_quality, at: p.generated_at, report: p.report };
    const previous = summary.trend[i - 1];
    if (previous && previous.comparable_key === p.comparable_key) segments[segments.length - 1]?.push(point);
    else {
      if (previous) breaks.push((x(i - 1) + x(i)) / 2);
      segments.push([point]);
    }
  });
  return { segments, breaks };
}
