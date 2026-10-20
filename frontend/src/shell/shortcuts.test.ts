import { describe, expect, it } from "vitest";

import { isTyping, resolveKey } from "./shortcuts";

describe("keyboard shortcuts (Phase U11)", () => {
  it("resolves single keys and two-key sequences", () => {
    expect(resolveKey("n", "")).toMatchObject({ to: "#/" });
    expect(resolveKey("g", "")).toBe("pending");
    expect(resolveKey("l", "g")).toMatchObject({ to: "#/library" });
    expect(resolveKey("?", "")).toMatchObject({ to: "help" });
  });

  it("ignores keys that are not shortcuts", () => {
    expect(resolveKey("x", "")).toBeNull();
    expect(resolveKey("x", "g")).toBeNull();
  });

  it("never fires while the person is typing", () => {
    expect(isTyping({ tagName: "INPUT" } as unknown as EventTarget)).toBe(true);
    expect(isTyping({ tagName: "TEXTAREA" } as unknown as EventTarget)).toBe(true);
    expect(isTyping({ tagName: "DIV", isContentEditable: true } as unknown as EventTarget)).toBe(true);
    expect(isTyping({ tagName: "BUTTON" } as unknown as EventTarget)).toBe(false);
    expect(isTyping(null)).toBe(false);
  });
});
