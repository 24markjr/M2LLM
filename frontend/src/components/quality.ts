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
