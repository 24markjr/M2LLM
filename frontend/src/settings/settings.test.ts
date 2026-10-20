import { describe, expect, it } from "vitest";

import type { MissionSummary } from "../api/types";
import { olderThan } from "./settings";

const m = (run_id: string, status: string, created_at: string, finished_at: string | null = null) =>
  ({ run_id, status, created_at, finished_at }) as MissionSummary;

const NOW = new Date("2026-10-21T12:00:00Z");

describe("retention (Phase U10)", () => {
  it("selects finished investigations older than the period, by when they ended", () => {
    const missions = [
      m("old", "COMPLETED", "2026-09-01T00:00:00Z", "2026-09-01T00:05:00Z"),
      m("recent", "COMPLETED", "2026-10-20T00:00:00Z", "2026-10-20T00:05:00Z"),
      m("old-failed", "FAILED", "2026-08-01T00:00:00Z"),
      m("ended-late", "COMPLETED", "2026-09-01T00:00:00Z", "2026-10-15T00:00:00Z"),
    ];
    expect(olderThan(missions, 30, NOW).map((x) => x.run_id)).toEqual(["old", "old-failed"]);
  });

  it("never selects a running investigation, however old", () => {
    expect(olderThan([m("running", "RUNNING", "2025-01-01T00:00:00Z")], 7, NOW)).toEqual([]);
  });
});
