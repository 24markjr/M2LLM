/**
 * Confidence as the console explains it (Phase 46). Pure, so it is tested without rendering.
 *
 * The numbers come from the finding's stored factors; nothing here recomputes a confidence. What it
 * adds is the arithmetic laid out, so "why 0.73?" reads as numbers that add up.
 */

import type { Confidence, ConfidenceFactor } from "../api/types";

export interface FactorRow {
  name: string;
  value: string;
  weight: string;
  contribution: string;
  reason: string;
  assessed: boolean;
}

function words(name: string): string {
  return name.replace(/_/g, " ");
}

/** One row per factor, in the order the engine applied them. */
export function factorRows(confidence: Confidence): FactorRow[] {
  return (confidence.factors ?? []).map((f: ConfidenceFactor) => ({
    name: words(f.name),
    value: f.value.toFixed(2),
    weight: f.weight > 0 ? f.weight.toFixed(2) : f.name === "resolution" ? "gate" : f.contribution < 0 ? "penalty" : "-",
    contribution: f.contribution === 0 && !f.assessed ? "not counted" : signed(f.contribution),
    reason: f.reason,
    assessed: f.assessed,
  }));
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}`;
}

/** "0.79 = 1.00 × 0.79 − 0.00", with the cap when it applied. Empty for a confidence without factors
 * (computed before Phase 46). */
export function confidenceSum(confidence: Confidence): string {
  if (!confidence.factors || confidence.factors.length === 0) return "";
  const weighted = confidence.weighted ?? 0;
  const penalty = confidence.penalty ?? 0;
  const raw = confidence.resolution_rate * weighted - penalty;
  const capped = raw > confidence.value + 1e-9;
  return (
    `${confidence.value.toFixed(2)} = resolution ${confidence.resolution_rate.toFixed(2)} × weighted ${weighted.toFixed(2)}` +
    (penalty ? ` − penalty ${penalty.toFixed(2)}` : "") +
    (capped ? ` = ${raw.toFixed(2)}, capped at ${confidence.classification_ceiling.toFixed(2)}` : "")
  );
}

/** What held the number down, largest first: each weighted factor's shortfall from 1. */
export function costs(confidence: Confidence): { name: string; cost: number }[] {
  const resolution = confidence.resolution_rate;
  return (confidence.factors ?? [])
    .filter((f) => f.weight > 0 && f.value < 1)
    .map((f) => ({ name: words(f.name), cost: resolution * f.weight * (1 - f.value) }))
    .filter((c) => c.cost >= 0.005)
    .sort((a, b) => b.cost - a.cost);
}

/**
 * A label for a confidence value (v4 Phase 2). The value is an evidence score - how much and how
 * good the evidence is - and has not been shown to be calibrated: nobody has measured that findings
 * scored 0.8 are right four times in five. So the console says what the score is, in words, and
 * shows the number only where its factors explain it, never as a percentage that reads as a
 * probability.
 */
export const SCORE_NOTE = "An evidence score from named factors, not a probability: calibration has not been measured.";

export function evidenceLabel(value: number): string {
  if (value <= 0) return "no evidence";
  if (value >= 0.7) return "strong evidence";
  if (value >= 0.4) return "moderate evidence";
  return "weak evidence";
}
