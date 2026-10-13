import { describe, expect, it } from "vitest";

import { applyTheme, loadTheme, parseTheme, saveTheme, THEME_KEY, type ThemeStorage } from "./theme";

function memory(initial: Record<string, string> = {}): ThemeStorage & { data: Record<string, string> } {
  const data = { ...initial };
  return { data, getItem: (k) => data[k] ?? null, setItem: (k, v) => void (data[k] = v) };
}

const refusing: ThemeStorage = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
};

describe("theme (Phase U2)", () => {
  it("is light unless dark was chosen", () => {
    expect(loadTheme(memory())).toBe("light");
    expect(loadTheme(memory({ [THEME_KEY]: "dark" }))).toBe("dark");
    expect(parseTheme("solarized")).toBe("light");
    expect(loadTheme(null)).toBe("light");
  });

  it("remembers the choice", () => {
    const storage = memory();
    saveTheme(storage, "dark");
    expect(loadTheme(storage)).toBe("dark");
  });

  it("falls back to light when storage is refused", () => {
    expect(loadTheme(refusing)).toBe("light");
    expect(() => saveTheme(refusing, "dark")).not.toThrow();
  });

  it("sets data-theme on the root", () => {
    const root = { dataset: {} as DOMStringMap };
    applyTheme("dark", root);
    expect(root.dataset.theme).toBe("dark");
  });
});
