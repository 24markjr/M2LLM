/**
 * Settings (Phase U10), apart from React: what a retention period would delete.
 *
 * Retention is applied by the person, from Settings, never on a timer: it lists the investigations
 * that would go, and each is then deleted through the same audited route as a single delete. A
 * running investigation is never selected, however old.
 */

import type { MissionSummary } from "../api/types";

const FINISHED = new Set(["COMPLETED", "FAILED", "CANCELLED", "CLARIFICATION_NEEDED"]);
const DAY_MS = 24 * 60 * 60 * 1000;

export const RETENTION_DAYS = [7, 30, 90, 365] as const;

/** Finished investigations that ended (or, without an end, began) more than `days` ago. */
export function olderThan(missions: MissionSummary[], days: number, now: Date): MissionSummary[] {
  const cutoff = now.getTime() - days * DAY_MS;
  return missions.filter((m) => {
    if (!FINISHED.has(m.status)) return false;
    const at = Date.parse(m.finished_at ?? m.created_at);
    return Number.isFinite(at) && at < cutoff;
  });
}
