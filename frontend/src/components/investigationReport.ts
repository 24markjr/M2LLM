/** The investigation report as the console summarises it (Phase 51). Pure, so it is tested. */

import type { InvestigationReport } from "../api/types";

/** "2 established · 1 awaiting review · 3 not established". */
export function reportCounts(report: InvestigationReport): string {
  return [
    `${report.established.length} established`,
    `${report.awaiting_review.length} awaiting review`,
    `${report.not_established.length} not established`,
  ].join(" · ");
}
