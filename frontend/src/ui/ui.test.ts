import { describe, expect, it } from "vitest";

import { STATUS, statusOf } from "./status";
import { nextTab } from "./tabs";
import { MAX_TOASTS, TOAST_MS, toastReducer, type Toast } from "./toast";

describe("status marks (Phase U2)", () => {
  it("maps verification results to a status with a word and a glyph", () => {
    expect(statusOf("SUPPORTED")).toBe("verified");
    expect(statusOf("PARTIALLY_SUPPORTED")).toBe("inferred");
    expect(statusOf("UNSUPPORTED")).toBe("unsupported");
    expect(statusOf(undefined)).toBe("unknown");
    for (const meta of Object.values(STATUS)) {
      expect(meta.label && meta.glyph && meta.description).toBeTruthy();
    }
  });
});

describe("toasts (Phase U2)", () => {
  const toast = (id: number): Toast => ({ id, tone: "info", message: `t${id}` });

  it("keeps the newest few and dismisses by id", () => {
    let state: Toast[] = [];
    for (let id = 1; id <= MAX_TOASTS + 2; id++) state = toastReducer(state, { type: "add", toast: toast(id) });
    expect(state.map((t) => t.id)).toEqual([3, 4, 5, 6]);
    expect(toastReducer(state, { type: "dismiss", id: 4 }).map((t) => t.id)).toEqual([3, 5, 6]);
  });

  it("leaves an error up until it is dismissed", () => {
    expect(TOAST_MS.error).toBeNull();
    expect(TOAST_MS.success).toBeGreaterThan(0);
  });
});

describe("tabs (Phase U2)", () => {
  it("moves with the arrow keys, wraps, and jumps with Home and End", () => {
    expect(nextTab("ArrowRight", 0, 3)).toBe(1);
    expect(nextTab("ArrowRight", 2, 3)).toBe(0);
    expect(nextTab("ArrowLeft", 0, 3)).toBe(2);
    expect(nextTab("Home", 2, 3)).toBe(0);
    expect(nextTab("End", 0, 3)).toBe(2);
    expect(nextTab("a", 1, 3)).toBeNull();
  });
});
