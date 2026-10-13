/**
 * The top bar (Phase U3): where you are, and the controls that apply everywhere - search, the
 * light/dark switch and Settings. On a phone it also opens the sidebar.
 */

import { SettingsMenu } from "../components/SettingsMenu";
import { useTheme } from "../theme/ThemeProvider";
import { IconChevronRight, IconMenu, IconMoon, IconSearch, IconSun } from "../ui/icons";

/** The link for each trail item that is a place of its own. */
const TRAIL_LINKS: Record<string, string> = {
  Home: "#/",
  Cases: "#/cases",
  Library: "#/library",
  Insights: "#/insights",
  Activity: "#/activity",
  "New investigation": "#/",
};

export function TopBar({
  trail,
  onMenu,
  onSearch,
}: {
  trail: string[];
  onMenu: () => void;
  onSearch: () => void;
}) {
  const { theme, setTheme } = useTheme();
  return (
    <header className="topbar">
      <button type="button" className="icon-button topbar-menu" aria-label="Open the sidebar" onClick={onMenu}>
        <IconMenu />
      </button>
      <nav className="trail" aria-label="You are here">
        <ol>
          {trail.map((part, i) => {
            const last = i === trail.length - 1;
            const href = TRAIL_LINKS[part];
            return (
              <li key={`${part}-${i}`}>
                {i > 0 ? <IconChevronRight size={14} /> : null}
                {href && !last ? (
                  <a href={href}>{part}</a>
                ) : (
                  <span className={last ? "trail-here" : undefined} aria-current={last ? "page" : undefined}>
                    {part}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="topbar-tools">
        <button type="button" className="topbar-search" onClick={onSearch} aria-label="Search (Ctrl+K)">
          <IconSearch size={16} />
          <span>Search cases and pages</span>
          <kbd>Ctrl K</kbd>
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label={theme === "light" ? "Switch to dark" : "Switch to light"}
          title={theme === "light" ? "Dark theme" : "Light theme"}
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        >
          {theme === "light" ? <IconMoon /> : <IconSun />}
        </button>
        <SettingsMenu />
      </div>
    </header>
  );
}
