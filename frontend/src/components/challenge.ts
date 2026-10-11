/** Challenge results as the console shows them (Phase 48). Pure, so they are tested without rendering. */

import type { ChallengeResult } from "../api/types";

/** "0.84 → 0.10" with the change: what the challenge did to the number. */
export function challengeDelta(result: ChallengeResult): string {
  const change = result.confidence_after - result.confidence_before;
  const sign = change > 0 ? "+" : change < 0 ? "−" : "±";
  return `confidence ${result.confidence_before.toFixed(2)} → ${result.confidence_after.toFixed(2)} (${sign}${Math.abs(change).toFixed(2)})`;
}
