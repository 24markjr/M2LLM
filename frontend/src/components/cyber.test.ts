import { describe, expect, it } from "vitest";

import type { CyberAnalysis } from "../api/types";
import { hasEvents, indicatorsByKind, relationText } from "./cyber";

const analysis: CyberAnalysis = {
  events: 5,
  documents: ["cyber_lateral_movement.jsonl"],
  indicators: [
    { kind: "ipv4", value: "10.0.0.12", defanged: false, sources: ["x:r1"], via: [] },
    { kind: "file_path", value: "C:\\Windows\\Temp\\x.dll", defanged: false, sources: ["x:r5"], via: [] },
    { kind: "ipv4", value: "10.0.0.31", defanged: false, sources: ["x:r4"], via: [] },
  ],
  entities: [],
  relations: [],
  host_timelines: {},
  account_timelines: {},
  decoded_commands: [],
  similar_cases: [],
  recall: "off: the case has not opted in to recall",
};

describe("cyber (Phase 52)", () => {
  it("writes a relation in words, with its detail", () => {
    expect(
      relationText({
        subject: "host:ws-12",
        predicate: "CONNECTED_TO",
        object: "ipv4:203.0.113.50",
        sources: [],
        first_seen: "",
        last_seen: "",
        detail: "port 80",
      }),
    ).toBe("host ws-12 CONNECTED TO ipv4 203.0.113.50 (port 80)");
  });

  it("groups indicators by kind", () => {
    expect(indicatorsByKind(analysis)).toEqual([
      ["file_path", ["C:\\Windows\\Temp\\x.dll"]],
      ["ipv4", ["10.0.0.12", "10.0.0.31"]],
    ]);
  });

  it("shows a panel only when the documents held events", () => {
    expect(hasEvents(analysis)).toBe(true);
    expect(hasEvents({ ...analysis, events: 0 })).toBe(false);
    expect(hasEvents(null)).toBe(false);
  });
});
