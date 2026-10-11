/** Review states as the console shows them (Phase 50). Pure, so they are tested without rendering. */

import type { AuditEntry, FindingReview } from "../api/types";

/** The badge text: "REVIEW: PENDING", or nothing when the finding needs no review and has none. */
export function reviewBadge(review: FindingReview | undefined): string {
  if (!review) return "";
  if (!review.required && review.history.length === 0) return "";
  return `REVIEW: ${review.state}`;
}

/** Why it needs a person, and who decided last. */
export function reviewSummary(review: FindingReview): string {
  const why = review.required_because.length
    ? `needs review: ${review.required_because.join("; ")}`
    : "needs no review";
  const last = review.history[review.history.length - 1];
  if (!last) return why;
  return `${why} · ${last.state.toLowerCase()} by ${last.reviewer}${last.reason ? `: ${last.reason}` : ""}`;
}

/** One audit line: "POST /api/v1/missions → 202, by analyst-7". */
export function auditLine(entry: AuditEntry): string {
  const outcome = entry.status_code === null ? "" : ` → ${entry.status_code}`;
  return `${entry.action}${outcome}, by ${entry.actor}`;
}
