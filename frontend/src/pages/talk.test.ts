import { describe, expect, it } from "vitest";

import type { ToolStep, Turn } from "../api/types";
import { pendingQuestion, stopLabel, toolSummary } from "./talk";

const step = (tool: string): ToolStep => ({ tool, arguments: {}, result: "" });

describe("the investigation conversation (v4 Phase 3)", () => {
  it("says why an answer stopped, and nothing when it simply answered", () => {
    expect(stopLabel("ANSWERED")).toBe("");
    expect(stopLabel("STEP_LIMIT")).toContain("five lookups");
    expect(stopLabel("ASKED_USER")).toBe("needs your answer");
  });

  it("summarises the tools an answer rests on", () => {
    expect(toolSummary([step("search_evidence"), step("search_evidence"), step("read_span"), step("calculate")])).toBe(
      "searched 2×, read 1 passage, calculated",
    );
    expect(toolSummary([])).toBe("");
  });

  it("knows when the assistant is waiting on the person", () => {
    const asked = { role: "assistant", stop_reason: "ASKED_USER", question: "Which contract?" } as Turn;
    expect(pendingQuestion([asked])).toBe("Which contract?");
    expect(pendingQuestion([{ ...asked, stop_reason: "ANSWERED" }])).toBe("");
    expect(pendingQuestion([])).toBe("");
  });
});

describe("a streamed answer (v4 Phase 4)", () => {
  it("parses server-sent events across chunk boundaries", async () => {
    const { parseEvents } = await import("../api/stream");
    const first = parseEvents('data: {"type":"activity","text":"Reading"}\n\ndata: {"type":"wo');
    expect(first.events).toEqual([{ type: "activity", text: "Reading" }]);
    const second = parseEvents(first.rest + 'rds","claim":0,"text":"Aurora "}\n\n');
    expect(second.events).toEqual([{ type: "words", claim: 0, text: "Aurora " }]);
    expect(second.rest).toBe("");
  });

  it("builds claims word by word, and marks each once it is checked", async () => {
    const { liveClaims } = await import("./talk");
    let live = liveClaims({ question: "q", activity: "", claims: [] }, { type: "words", claim: 0, text: "Due on " });
    live = liveClaims(live, { type: "words", claim: 0, text: "30 April. " });
    expect(live?.claims[0]).toMatchObject({ text: "Due on 30 April. ", status: "" });
    live = liveClaims(live, { type: "verdict", claim: 0, status: "SUPPORTED", citations: ["r.txt:r2"] });
    expect(live?.claims[0]).toMatchObject({ status: "SUPPORTED", citations: ["r.txt:r2"] });
    expect(liveClaims(live, { type: "activity", text: "Checking 1 claim(s)" })?.activity).toBe("Checking 1 claim(s)");
  });

  it("opens a line citation at its line", async () => {
    const { parseLocator } = await import("../components/SourceViewer");
    expect(parseLocator("report.txt:r12")).toEqual({ document: "report.txt", line: 12 });
    expect(parseLocator("scan.pdf:p3")).toEqual({ document: "scan.pdf", line: null });
    expect(parseLocator("a:b.txt:r4")).toEqual({ document: "a:b.txt", line: 4 });
  });
});
