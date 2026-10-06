import { describe, expect, it } from "vitest";

import {
  documentsLink,
  draftFromHash,
  newMissionLink,
  objectiveFromSearch,
  shortHash,
  validWorkspace,
} from "./workspaces";

describe("workspaces", () => {
  it("accepts only the names the server accepts", () => {
    expect(validWorkspace("helix_2026-q3")).toBe(true);
    expect(validWorkspace("")).toBe(false);
    expect(validWorkspace("../etc")).toBe(false);
    expect(validWorkspace("a".repeat(65))).toBe(false);
  });

  it("round-trips a mission draft through a link", () => {
    const draft = {
      objective: "Investigate: budget & dates?",
      documents: ["helix report.txt", "ledger.xlsx"],
      workspace: "helix",
    };
    const link = newMissionLink(draft);
    expect(link.startsWith("#/new?")).toBe(true);
    expect(draftFromHash(link)).toEqual(draft);
  });

  it("leaves absent fields absent, and drops a bad workspace", () => {
    expect(newMissionLink({})).toBe("#/new");
    expect(draftFromHash("#/new")).toEqual({});
    expect(draftFromHash("#/new?workspace=..%2Fx")).toEqual({});
  });

  it("links to a workspace, and to the default without a parameter", () => {
    expect(documentsLink("helix")).toBe("#/documents?workspace=helix");
    expect(documentsLink("default")).toBe("#/documents");
    expect(documentsLink()).toBe("#/documents");
  });

  it("shows hashes short and turns a search into an objective", () => {
    expect(shortHash("abcdef0123456789")).toBe("abcdef012345");
    expect(shortHash("")).toBe("-");
    expect(objectiveFromSearch("  late shipments ")).toBe("Investigate: late shipments");
    expect(objectiveFromSearch(" ")).toBe("");
  });
});
