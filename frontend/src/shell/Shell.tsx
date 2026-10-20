/**
 * The application shell (Phase U3): sidebar, top bar, the page, and Ctrl+K.
 *
 * Wide screens: the sidebar sits beside the page and can be collapsed to a rail (remembered per
 * browser). Below 1024 px it is a drawer opened from the top bar, closed by choosing a page, by
 * Escape, or by tapping outside it.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "../api/client";
import { browserStorage } from "../theme/theme";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { type Route, sectionOf, trailOf } from "./routes";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

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
              The engine is not reachable. Start it from <code>backend/</code> with{" "}
              <code>uvicorn app.api.app:create_app --factory --reload</code>
            </div>
          ) : null}
          <div className="shell-content">
            <ErrorBoundary key={JSON.stringify(route)}>{children}</ErrorBoundary>
          </div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
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
