/**
 * The Settings button and its menu (Phase U2). Appearance first - light (the default) or dark -
 * remembered in this browser. U10 grows this into the full Settings area.
 */

import { useEffect, useRef, useState } from "react";

import { useTheme } from "../theme/ThemeProvider";
import type { Theme } from "../theme/theme";
import { IconMoon, IconSettings, IconSun } from "../ui/icons";

const CHOICES: { theme: Theme; label: string; Icon: typeof IconSun }[] = [
  { theme: "light", label: "Light", Icon: IconSun },
  { theme: "dark", label: "Dark", Icon: IconMoon },
];

export function SettingsMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div className="settings" ref={box}>
      <button
        type="button"
        className="icon-button"
        aria-label="Settings"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <IconSettings />
      </button>
      {open ? (
        <div className="settings-menu" role="dialog" aria-label="Settings">
          <div className="settings-section">
            <div className="settings-label" id="appearance-label">
              Appearance
            </div>
            <div className="segmented" role="radiogroup" aria-labelledby="appearance-label">
              {CHOICES.map(({ theme: value, label, Icon }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={theme === value}
                  className={theme === value ? "on" : ""}
                  onClick={() => setTheme(value)}
                >
                  <Icon size={16} /> {label}
                </button>
              ))}
            </div>
          </div>
          <a className="settings-link" href="#/settings" onClick={() => setOpen(false)}>
            All settings
          </a>
          <a className="settings-link" href="#/design" onClick={() => setOpen(false)}>
            Design system: every component
          </a>
        </div>
      ) : null}
    </div>
  );
}
