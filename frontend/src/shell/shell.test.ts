import { describe, expect, it } from "vitest";

import { groupCases, parseRoute, sectionOf, trailOf } from "./routes";

const NOW = new Date(2026, 9, 13, 15, 0, 0);

function c(id: string, opened: Date, pinned = false) {
  return { case: { case_id: id, title: id, opened_at: opened.toISOString(), pinned } };
}

describe("the shell (Phase U3)", () => {
  it("opens the old addresses inside the merged pages", () => {
    expect(sectionOf(parseRoute("#/evidence"))).toBe("library");
    expect(sectionOf(parseRoute("#/documents"))).toBe("library");
    expect(sectionOf(parseRoute("#/library"))).toBe("library");
    expect(sectionOf(parseRoute("#/evaluation"))).toBe("insights");
    expect(sectionOf(parseRoute("#/memory?entity=Rahul"))).toBe("insights");
    expect(sectionOf(parseRoute("#/replay"))).toBe("insights");
    expect(sectionOf(parseRoute("#/insights"))).toBe("insights");
    expect(sectionOf(parseRoute("#/activity"))).toBe("activity");
    expect(sectionOf(parseRoute("#/knowledge"))).toBe("new");
    expect(sectionOf(parseRoute("#/"))).toBe("cases");
    expect(sectionOf(parseRoute("#/mission/run_0123456789ab"))).toBe("cases");
  });

  it("names where every page sits", () => {
    expect(trailOf(parseRoute("#/case/CASE-2026-00010"))).toEqual(["Cases", "CASE-2026-00010"]);
    expect(trailOf(parseRoute("#/mission/run_0123456789ab/graph"))).toEqual([
      "Investigations",
      "run_0123456789ab",
      "Knowledge graph",
    ]);
    expect(trailOf(parseRoute("#/replay"))).toEqual(["Insights", "Recordings"]);
  });

  it("groups cases pinned first, then today, this week and earlier", () => {
    const groups = groupCases(
      [
        c("a", new Date(2026, 9, 13, 9)),
        c("b", new Date(2026, 9, 10)),
        c("p", new Date(2026, 0, 1), true),
        c("e", new Date(2026, 8, 1)),
        c("y", new Date(2026, 9, 12, 23)),
      ],
      NOW,
    );
    const ids = (xs: { case: { case_id: string } }[]) => xs.map((x) => x.case.case_id);
    expect(ids(groups.pinned)).toEqual(["p"]);
    expect(ids(groups.today)).toEqual(["a"]);
    expect(ids(groups.week)).toEqual(["b", "y"]);
    expect(ids(groups.earlier)).toEqual(["e"]);
  });
});
