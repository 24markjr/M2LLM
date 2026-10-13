/**
 * The theme (Phase U2): light by default, dark when chosen in Settings. Remembered per browser.
 *
 * Storage can be missing or refuse access (private windows, blocked site data), so every read and
 * write is guarded and the default holds when it fails.
 */

export type Theme = "light" | "dark";

export const DEFAULT_THEME: Theme = "light";
export const THEME_KEY = "jarvis.theme";

/** The minimal storage this needs; `window.localStorage` in the app, a stub in tests. */
export interface ThemeStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function parseTheme(value: string | null | undefined): Theme {
  return value === "dark" || value === "light" ? value : DEFAULT_THEME;
}

export function loadTheme(storage: ThemeStorage | null): Theme {
  try {
    return parseTheme(storage?.getItem(THEME_KEY));
  } catch {
    return DEFAULT_THEME;
  }
}

export function saveTheme(storage: ThemeStorage | null, theme: Theme): void {
  try {
    storage?.setItem(THEME_KEY, theme);
  } catch {
    /* not remembered; the theme still applies for this visit */
  }
}

/** The browser's storage, or null when the browser refuses it. */
export function browserStorage(): ThemeStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Put the theme on <html>: the tokens switch on `data-theme`. */
export function applyTheme(theme: Theme, root: { dataset: DOMStringMap } | null = null): void {
  const target = root ?? (typeof document === "undefined" ? null : document.documentElement);
  if (target) target.dataset.theme = theme;
}
