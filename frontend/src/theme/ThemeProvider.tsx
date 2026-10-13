/**
 * The current theme for every component, and the way to change it (Phase U2).
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { applyTheme, browserStorage, loadTheme, saveTheme, type Theme } from "./theme";

interface ThemeValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeValue>({ theme: "light", setTheme: () => undefined });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => loadTheme(browserStorage()));

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next);
    saveTheme(browserStorage(), next);
    setThemeState(next);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
