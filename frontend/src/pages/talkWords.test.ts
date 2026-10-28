import { describe, expect, it } from "vitest";

import { parseEvents } from "../api/stream";
import { parseLocator, withoutMarker } from "../components/SourceViewer";
import { liveClaims } from "./talk";
import { talkWords } from "./talkWords";

describe("Indian languages in the console (v4 Phases 6-7)", () => {
  it("speaks Hindi when Hindi is chosen, and English for a language it has no words for", () => {
    expect(talkWords("hi").ask).toBe("पूछें");
    expect(talkWords("hi").translationLabel).toContain("मशीनी अनुवाद");
    expect(talkWords("ta")).toEqual(talkWords("en"));
    expect(talkWords("").ask).toBe("Ask");
  });

  it("gives every word in both languages", () => {
    const english = Object.keys(talkWords("en")).sort();
    expect(Object.keys(talkWords("hi")).sort()).toEqual(english);
    for (const value of Object.values(talkWords("hi"))) expect(value.trim()).not.toBe("");
  });

  it("shows a translated line without its marker, and a citation's line in both columns", () => {
    expect(withoutMarker("[translated:hi] The work was completed on 15 May 2026.")).toBe(
      "The work was completed on 15 May 2026.",
    );
    expect(withoutMarker("Invoice INV-22 attached.")).toBe("Invoice INV-22 attached.");
    expect(parseLocator("report_hi.txt:r7")).toEqual({ document: "report_hi.txt", line: 7 });
  });

  it("reads the translation event off the stream without disturbing the live answer", () => {
    const { events } = parseEvents(
      'data: {"type":"translation","language":"hi","language_name":"Hindi","speech":"hi-IN","text":"नमस्ते","engine":"indictrans2","engine_version":"v","fallback":false,"label":"x"}\n\n',
    );
    expect(events[0]?.type).toBe("translation");
    const live = { question: "q", activity: "Translating", claims: [] };
    expect(liveClaims(live, events[0]!)).toBe(live);
  });
});
