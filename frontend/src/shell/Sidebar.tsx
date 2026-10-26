/**
 * The sidebar (Phase U3): start an investigation, find one, and every case - pinned first, then by
 * when it was opened - with pin, rename and delete. Library, Insights and Activity at the foot, with
 * the engine's state.
 */

import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { useUser } from "../auth/AuthGate";
import type { CaseList } from "../api/types";
import { Button, ConfirmDialog, Dialog, TextInput, useToast } from "../ui/components";
import {
  IconActivity,
  IconSettings,
  IconEdit,
  IconFolder,
  IconInsights,
  IconLibrary,
  IconLogo,
  IconMore,
  IconPin,
  IconPlus,
  IconSearch,
  IconSidebar,
  IconTrash,
} from "../ui/icons";
import { groupCases, type Section } from "./routes";

type CaseRow = CaseList["cases"][number];

export const CASES_CHANGED = "jarvis:cases-changed";

/** Tell the sidebar the case list changed (a case opened, renamed, deleted elsewhere). */
export function casesChanged(): void {
  window.dispatchEvent(new Event(CASES_CHANGED));
}

export function Sidebar({
  section,
  activeCase,
  collapsed,
  engine,
  onToggleCollapsed,
  onSearch,
  onNavigate,
}: {
  section: Section;
  activeCase: string;
  collapsed: boolean;
  engine: { model: string; healthy: boolean } | null | "unreachable";
  onToggleCollapsed: () => void;
  onSearch: () => void;
  onNavigate: () => void;
}) {
  const { user, signOut } = useUser();
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const load = () =>
      api
        .listCases()
        .then((body) => {
          setCases(body.cases);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    load();
    window.addEventListener(CASES_CHANGED, load);
    return () => window.removeEventListener(CASES_CHANGED, load);
  }, []);

  const groups = groupCases(cases, new Date());
  const sections: [string, CaseRow[]][] = [
    ["Pinned", groups.pinned],
    ["Today", groups.today],
    ["Previous 7 days", groups.week],
    ["Earlier", groups.earlier],
  ];

  return (
    <nav className={`sidebar ${collapsed ? "collapsed" : ""}`} aria-label="Main">
      <div className="sidebar-head">
        <a className="sidebar-brand" href="#/" onClick={onNavigate} aria-label="JARVIS - home">
          <IconLogo />
          <span className="sidebar-label">JARVIS</span>
        </a>
        <button
          type="button"
          className="icon-button sidebar-collapse"
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          onClick={onToggleCollapsed}
        >
          <IconSidebar />
        </button>
      </div>

      <div className="sidebar-actions">
        <a className={`sidebar-new ${section === "new" ? "on" : ""}`} href="#/" onClick={onNavigate} title="New investigation">
          <IconPlus size={18} />
          <span className="sidebar-label">New investigation</span>
        </a>
        <button type="button" className="sidebar-item" onClick={onSearch} title="Search (Ctrl+K)">
          <IconSearch size={18} />
          <span className="sidebar-label">Search</span>
          <kbd className="sidebar-label">Ctrl K</kbd>
        </button>
      </div>

      <div className="sidebar-scroll">
        {!collapsed ? (
          <>
            {failed ? <p className="sidebar-note">Cases could not be loaded.</p> : null}
            {!failed && cases.length === 0 ? (
              <p className="sidebar-note">No cases yet. Start a new investigation, or open a case from Cases.</p>
            ) : null}
            {sections.map(([title, rows]) =>
              rows.length ? (
                <div className="sidebar-group" key={title}>
                  <div className="sidebar-group-title">{title}</div>
                  {rows.map((row) => (
                    <CaseItem key={row.case.case_id} row={row} active={row.case.case_id === activeCase} onNavigate={onNavigate} />
                  ))}
                </div>
              ) : null,
            )}
            <a className="sidebar-all" href="#/cases" onClick={onNavigate}>
              All cases
            </a>
          </>
        ) : (
          <a className={`sidebar-item ${section === "cases" ? "on" : ""}`} href="#/cases" onClick={onNavigate} title="Cases">
            <IconFolder size={18} />
          </a>
        )}
      </div>

      <div className="sidebar-foot">
        <SidebarLink href="#/library" icon={<IconLibrary size={18} />} label="Library" on={section === "library"} onNavigate={onNavigate} />
        <SidebarLink href="#/insights" icon={<IconInsights size={18} />} label="Insights" on={section === "insights"} onNavigate={onNavigate} />
        <SidebarLink href="#/activity" icon={<IconActivity size={18} />} label="Activity" on={section === "activity"} onNavigate={onNavigate} />
        <SidebarLink href="#/settings" icon={<IconSettings size={18} />} label="Settings" on={section === "settings"} onNavigate={onNavigate} />
        {user ? (
          <div className="sidebar-user" title={`${user.email} · ${user.role}`}>
            <span className="sidebar-avatar" aria-hidden="true">
              {(user.name || user.email).slice(0, 1).toUpperCase()}
            </span>
            <span className="sidebar-label">
              {user.name || user.email}
              <span className="sidebar-role">{user.role}</span>
            </span>
            <button type="button" className="sidebar-signout sidebar-label" onClick={signOut}>
              Sign out
            </button>
          </div>
        ) : null}
        <div className="sidebar-engine" title={engineTitle(engine)}>
          <span className={`engine-dot ${engineState(engine)}`} aria-hidden="true" />
          <span className="sidebar-label">{engineLabel(engine)}</span>
        </div>
      </div>
    </nav>
  );
}

function SidebarLink({
  href,
  icon,
  label,
  on,
  onNavigate,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  on: boolean;
  onNavigate: () => void;
}) {
  return (
    <a className={`sidebar-item ${on ? "on" : ""}`} href={href} onClick={onNavigate} title={label} aria-current={on ? "page" : undefined}>
      {icon}
      <span className="sidebar-label">{label}</span>
    </a>
  );
}

function CaseItem({ row, active, onNavigate }: { row: CaseRow; active: boolean; onNavigate: () => void }) {
  const notify = useToast();
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [title, setTitle] = useState(row.case.title);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { case: item, counters } = row;

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setMenu(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", key);
    };
  }, [menu]);

  const act = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await work();
      notify(done, "success");
      casesChanged();
      return true;
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "That did not work.", "error");
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`sidebar-case ${active ? "on" : ""}`} ref={box}>
      <a href={`#/case/${item.case_id}`} onClick={onNavigate} aria-current={active ? "page" : undefined} title={item.title}>
        <span className="sidebar-case-title">{item.title}</span>
        {counters.running ? <span className="sidebar-case-live" aria-label="investigation running" /> : null}
      </a>
      <button
        type="button"
        className="icon-button sidebar-case-more"
        aria-label={`Actions for ${item.title}`}
        aria-haspopup="menu"
        aria-expanded={menu}
        onClick={() => setMenu((m) => !m)}
      >
        <IconMore size={16} />
      </button>
      {menu ? (
        <div className="menu" role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setMenu(false);
              void act(() => api.updateCase(item.case_id, { pinned: !item.pinned }), item.pinned ? "Unpinned." : "Pinned to the top.");
            }}
          >
            <IconPin size={16} /> {item.pinned ? "Unpin" : "Pin"}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setMenu(false);
              setTitle(item.title);
              setRenaming(true);
            }}
          >
            <IconEdit size={16} /> Rename
          </button>
          <button
            type="button"
            role="menuitem"
            className="danger"
            onClick={() => {
              setMenu(false);
              setDeleting(true);
            }}
          >
            <IconTrash size={16} /> Delete
          </button>
        </div>
      ) : null}

      <Dialog
        open={renaming}
        title="Rename case"
        onClose={() => setRenaming(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRenaming(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              busy={busy}
              disabled={title.trim().length < 3}
              onClick={async () => {
                if (await act(() => api.updateCase(item.case_id, { title: title.trim() }), "Renamed.")) setRenaming(false);
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} hint="3 to 200 characters." autoFocus />
      </Dialog>

      <ConfirmDialog
        open={deleting}
        title={`Delete ${item.case_id}?`}
        busy={busy}
        body={
          <>
            <p>
              <strong>{item.title}</strong> and its {counters.investigations} investigation(s) will be deleted, with their
              recordings and memory.
            </p>
            <p>
              Kept: the evidence items ({counters.evidence}) in the Library, their chain of custody, review decisions and the
              audit log.
            </p>
          </>
        }
        confirmLabel="Delete case"
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          if (await act(() => api.deleteCase(item.case_id), `${item.case_id} deleted.`)) {
            setDeleting(false);
            if (active) window.location.hash = "#/";
          }
        }}
      />
    </div>
  );
}

type Engine = { model: string; healthy: boolean } | null | "unreachable";

function engineState(engine: Engine): string {
  if (engine === "unreachable") return "down";
  if (engine === null) return "";
  return engine.healthy ? "up" : "warn";
}

function engineLabel(engine: Engine): string {
  if (engine === "unreachable") return "Engine unreachable";
  if (engine === null) return "Checking the engine";
  return engine.healthy ? engine.model : `${engine.model} (not answering)`;
}

function engineTitle(engine: Engine): string {
  if (engine === "unreachable") return "Start the engine from backend/: uvicorn app.api.app:create_app --factory";
  return engineLabel(engine);
}
