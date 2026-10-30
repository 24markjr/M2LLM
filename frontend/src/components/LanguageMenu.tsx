/** The top bar's language button (v4 Phase 7): the console's language, one click away. */

import { useEffect, useRef, useState } from "react";

import { UI_LANGUAGES, shellWords, useUiLanguage } from "../i18n/uiLanguage";

export function LanguageMenu() {
  const [language, setLanguage] = useUiLanguage();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = UI_LANGUAGES.find((l) => l.code === language) ?? UI_LANGUAGES[0]!;
  const words = shellWords(language);

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
        className="language-button"
        aria-label={`${words.language}: ${current.name}`}
        title={`${words.language}: ${current.native}`}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true">अ/A</span> {current.short}
      </button>
      {open ? (
        <div className="settings-menu language-menu" role="dialog" aria-label={words.language}>
          <div className="settings-label">{words.language}</div>
          <ul role="listbox" aria-label={words.language}>
            {UI_LANGUAGES.map((l) => (
              <li key={l.code || "en"}>
                <button
                  type="button"
                  role="option"
                  aria-selected={l.code === language}
                  className={l.code === language ? "on" : ""}
                  onClick={() => {
                    setLanguage(l.code);
                    setOpen(false);
                  }}
                >
                  <span lang={l.code || "en"}>{l.native}</span>
                  <span className="dim">{l.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
