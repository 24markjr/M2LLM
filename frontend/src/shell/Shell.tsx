/**
 * The application shell (Phase U3): sidebar, top bar, the page, and Ctrl+K.
 *
 * Wide screens: the sidebar sits beside the page and can be collapsed to a rail (remembered per
 * browser). Below 1024 px it is a drawer opened from the top bar, closed by choosing a page, by
 * Escape, or by tapping outside it.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "../api/client";
import { browserStorage } from "../theme/theme";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { type Route, sectionOf, trailOf } from "./routes";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { reopenTour } from "../home/Tour";
import { Dialog } from "../ui/components";
import { isTyping, resolveKey, SHORTCUTS } from "./shortcuts";

const COLLAPSED_KEY = "jarvis.sidebar";

function loadCollapsed(): boolean {
  try {
    return browserStorage()?.getItem(COLLAPSED_KEY) === "collapsed";
  } catch {
    return false;
  }
}

export function Shell({ route, children }: { route: Route; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(loadCollapsed);
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  // The first key of a two-key shortcut ("g", then "l"), forgotten after a second.
  const pending = useRef({ key: "", at: 0 });
  const [engine, setEngine] = useState<{ model: string; healthy: boolean } | null | "unreachable">(null);

  useEffect(() => {
    api
      .health()
      .then((body) => setEngine({ model: body.model, healthy: body.provider_healthy }))
      .catch(() => setEngine("unreachable"));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      } else if (e.key === "Escape") {
        setDrawer(false);
      } else if (!e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
        const was = Date.now() - pending.current.at < 1000 ? pending.current.key : "";
        const hit = resolveKey(e.key, was);
        pending.current = hit === "pending" ? { key: e.key, at: Date.now() } : { key: "", at: 0 };
        if (hit === null || hit === "pending") return;
        e.preventDefault();
        if (hit.to === "help") setHelp(true);
        else if (hit.to === "search") setPalette(true);
        else window.location.hash = hit.to;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A new page closes the drawer and starts at the top.
  useEffect(() => {
    setDrawer(false);
    document.querySelector(".shell-main")?.scrollTo({ top: 0 });
  }, [route]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((was) => {
      const next = !was;
      try {
        browserStorage()?.setItem(COLLAPSED_KEY, next ? "collapsed" : "open");
      } catch {
        /* not remembered */
      }
      return next;
    });
  }, []);

  const activeCase = route.name === "case" ? route.caseId : "";

  return (
    <div className={`app-shell ${collapsed ? "rail" : ""} ${drawer ? "drawer-open" : ""}`}>
      <a className="skip-link" href="#main-content" onClick={(e) => {
        e.preventDefault();
        document.getElementById("main-content")?.focus();
      }}>
        Skip to content
      </a>
      <Sidebar
        section={sectionOf(route)}
        activeCase={activeCase}
        collapsed={collapsed && !drawer}
        engine={engine}
        onToggleCollapsed={drawer ? () => setDrawer(false) : toggleCollapsed}
        onSearch={() => setPalette(true)}
        onNavigate={() => setDrawer(false)}
      />
      {drawer ? <div className="drawer-backdrop" onClick={() => setDrawer(false)} aria-hidden="true" /> : null}
      <div className="shell-column">
        <TopBar trail={trailOf(route)} onMenu={() => setDrawer(true)} onSearch={() => setPalette(true)} />
        <main className="shell-main" id="main-content" tabIndex={-1}>
          {engine === "unreachable" ? (
            <div className="engine-banner" role="alert">
              The engine is not reachable. Start everything with <code>scripts\start-jarvis.ps1</code>, or the API alone from{" "}
              <code>backend/</code> with <code>uvicorn app.api.app:create_app --factory</code>, then reload.
            </div>
          ) : null}
          <div className="shell-content">
            <ErrorBoundary key={JSON.stringify(route)}>{children}</ErrorBoundary>
          </div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
      <Dialog open={help} title="Keyboard shortcuts" onClose={() => setHelp(false)}>
        <table className="shortcuts">
          <tbody>
            <tr>
              <td>
                <kbd>Ctrl</kbd> <kbd>K</kbd>
              </td>
              <td>Search everything</td>
            </tr>
            {SHORTCUTS.map((s) => (
              <tr key={s.keys}>
                <td>
                  {s.keys.split(" ").map((k, i) => (
                    <span key={i}>
                      {i ? " then " : ""}
                      <kbd>{k}</kbd>
                    </span>
                  ))}
                </td>
                <td>{s.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="shortcuts-note">Shortcuts never fire while you are typing in a field.</p>
        <button
          type="button"
          className="ui-button ghost sm"
          onClick={() => {
            reopenTour();
            window.location.hash = "#/";
            window.location.reload();
          }}
        >
          Show the welcome tour again
        </button>
      </Dialog>
    </div>
  );
}

/** The tabs over a merged page: each tab is an address, so links and the back button work. */
export function SectionTabs({ tabs, active }: { tabs: { href: string; label: string; id: string }[]; active: string }) {
  return (
    <div className="section-head">
      <nav className="section-tabs" aria-label="Sections">
        {tabs.map((t) => (
          <a key={t.id} href={t.href} className={t.id === active ? "on" : ""} aria-current={t.id === active ? "page" : undefined}>
            {t.label}
          </a>
        ))}
      </nav>
    </div>
  );
}

export const LIBRARY_TABS = [
  { id: "evidence", label: "Files", href: "#/evidence" },
  { id: "documents", label: "Workspaces", href: "#/documents" },
];

export const INSIGHTS_TABS = [
  { id: "evaluation", label: "Quality", href: "#/evaluation" },
  { id: "memory", label: "Memory", href: "#/memory" },
  { id: "replay", label: "Recordings", href: "#/replay" },
];
