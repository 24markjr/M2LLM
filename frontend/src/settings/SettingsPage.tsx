/**
 * Settings (Phase U10): appearance, the default domain pack, the engine (model, stores, offline),
 * activity, retention, and deleting everything. Every destructive action names what it removes and
 * what is kept, needs typing to confirm, and goes through the same audited routes as the console's
 * single deletes.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { MemoryStatus, MissionSummary, StoreStatus } from "../api/types";
import { PACK_KEY, PACKS } from "../home/packs";
import { casesChanged } from "../shell/Sidebar";
import { browserStorage } from "../theme/theme";
import { useTheme } from "../theme/ThemeProvider";
import { Badge, Button, ConfirmDialog, Notice, useToast } from "../ui/components";
import { AccountCard, PeopleCard } from "./People";
import { olderThan, RETENTION_DAYS } from "./settings";
import "./settings.css";

type Health = { status: string; model: string; provider_healthy: boolean };

function readPack(): string {
  try {
    return browserStorage()?.getItem(PACK_KEY) ?? "general";
  } catch {
    return "general";
  }
}

export function SettingsPage() {
  const notify = useToast();
  const { theme, setTheme } = useTheme();
  const [pack, setPack] = useState(readPack);
  const [health, setHealth] = useState<Health | null>(null);
  const [stores, setStores] = useState<StoreStatus[]>([]);
  const [memory, setMemory] = useState<MemoryStatus | null>(null);
  const [engineError, setEngineError] = useState("");
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const [days, setDays] = useState<number>(30);
  const [confirm, setConfirm] = useState<"" | "retention" | "all">("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.health().then(setHealth).catch((exc: unknown) => setEngineError(exc instanceof ApiError ? exc.message : "The engine did not answer."));
    api.getStores().then((s) => setStores(s.stores)).catch(() => setStores([]));
    api.getMemoryStatus().then(setMemory).catch(() => setMemory(null));
    api.listMissions().then(setMissions).catch(() => setMissions([]));
  }, []);
  useEffect(load, [load]);

  const choosePack = (id: string) => {
    setPack(id);
    try {
      browserStorage()?.setItem(PACK_KEY, id);
    } catch {
      // A preference; the home page falls back to General without it.
    }
    notify(`New investigations start in ${PACKS.find((p) => p.id === id)?.label ?? id}.`, "success");
  };

  const expiring = olderThan(missions, days, new Date());

  const applyRetention = async () => {
    setBusy(true);
    let deleted = 0;
    const failed: string[] = [];
    for (const m of expiring) {
      try {
        await api.deleteMission(m.run_id);
        deleted++;
      } catch {
        failed.push(m.run_id);
      }
    }
    notify(
      `${deleted} investigation(s) older than ${days} days deleted${failed.length ? `; ${failed.length} could not be` : ""}. Custody, reviews and the audit log are kept.`,
      failed.length ? "error" : "success",
    );
    setBusy(false);
    setConfirm("");
    casesChanged();
    load();
  };

  const deleteAll = async () => {
    setBusy(true);
    try {
      const report = await api.deleteAllMissions();
      const recordings = await api.deleteRecordings("all");
      notify(
        `${report.deleted.length} investigation(s) and ${recordings.deleted} recording(s) deleted; ${report.skipped.length} running ones skipped. Custody, reviews and the audit log are kept.`,
        "success",
      );
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "Not everything could be deleted.", "error");
    } finally {
      setBusy(false);
      setConfirm("");
      casesChanged();
      load();
    }
  };

  const online = health?.provider_healthy ?? false;

  return (
    <div className="settings">
      <h1>Settings</h1>

      <AccountCard />
      <PeopleCard />

      <section className="settings-card" aria-labelledby="s-appearance">
        <h2 id="s-appearance">Appearance</h2>
        <div className="settings-choice" role="radiogroup" aria-label="Theme">
          {(["light", "dark"] as const).map((t) => (
            <button key={t} type="button" role="radio" aria-checked={theme === t} className={theme === t ? "on" : ""} onClick={() => setTheme(t)}>
              {t === "light" ? "Light" : "Dark"}
            </button>
          ))}
        </div>
        <p className="settings-note">
          Remembered in this browser. <a href="#/design">See every component</a> in both themes.
        </p>
      </section>

      <section className="settings-card" aria-labelledby="s-domain">
        <h2 id="s-domain">Default domain</h2>
        <p className="settings-note">The domain pack a new investigation starts in: its starter questions, mode and sensitivity.</p>
        <div className="settings-packs">
          {PACKS.map((p) => (
            <label key={p.id} className={pack === p.id ? "on" : ""}>
              <input type="radio" name="pack" checked={pack === p.id} onChange={() => choosePack(p.id)} />
              <strong>{p.label}</strong>
              <span>{p.blurb}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="settings-card" aria-labelledby="s-engine">
        <h2 id="s-engine">Engine</h2>
        {engineError ? <Notice tone="error">{engineError}</Notice> : null}
        <dl className="settings-facts">
          <dt>Model</dt>
          <dd>
            <span className="mono">{health?.model ?? "-"}</span>{" "}
            <Badge tone={online ? "verified" : "unsupported"}>{online ? "answering" : "not answering"}</Badge>
          </dd>
          <dt>Where it runs</dt>
          <dd>On this computer, through Ollama. No document or question leaves the machine; the engine works offline.</dd>
          {stores.map((s) => (
            <div key={s.part} className="settings-fact-row">
              <dt>{s.part}</dt>
              <dd>
                <span className="mono">{s.store}</span>
                {s.note ? <span className="settings-note"> · {s.note}</span> : null}
              </dd>
            </div>
          ))}
          {memory ? (
            <>
              <dt>Memory</dt>
              <dd>
                episodes {memory.episodic ? "on" : "off"} · facts {memory.semantic_store || "unavailable"}
              </dd>
            </>
          ) : null}
        </dl>
        <Button size="sm" variant="ghost" onClick={load}>
          Check again
        </Button>
      </section>

      <section className="settings-card" aria-labelledby="s-activity">
        <h2 id="s-activity">Activity</h2>
        <p className="settings-note">
          Every review, deletion, filing and change is in the append-only audit log. <a href="#/audit">Open Activity</a>.
        </p>
      </section>

      <section className="settings-card" aria-labelledby="s-retention">
        <h2 id="s-retention">Retention</h2>
        <p className="settings-note">
          Delete finished investigations older than a period. Applied when you press the button, never on a timer. Running ones are never
          touched.
        </p>
        <div className="settings-row">
          <label>
            Older than{" "}
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {RETENTION_DAYS.map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <span className="settings-note">
            {expiring.length} of {missions.length} investigation(s) would be deleted.
          </span>
          <Button size="sm" variant="danger" disabled={expiring.length === 0 || busy} onClick={() => setConfirm("retention")}>
            Delete {expiring.length || ""} older
          </Button>
        </div>
      </section>

      <section className="settings-card danger" aria-labelledby="s-danger">
        <h2 id="s-danger">Delete everything</h2>
        <p className="settings-note">
          Every finished investigation, its recordings, archive, stored run and memory support. Kept, because they are append-only: the files
          in the Library and their chain of custody, review decisions and the audit log.
        </p>
        <Button variant="danger" disabled={busy} onClick={() => setConfirm("all")}>
          Delete all investigations
        </Button>
      </section>

      <ConfirmDialog
        open={confirm === "retention"}
        title={`Delete ${expiring.length} investigation(s) older than ${days} days?`}
        body={<p>Each is deleted as a single delete would: audited, with custody, reviews and the audit log kept.</p>}
        confirmLabel="Delete"
        busy={busy}
        onClose={() => setConfirm("")}
        onConfirm={() => void applyRetention()}
      />
      <ConfirmDialog
        open={confirm === "all"}
        title="Delete every investigation?"
        body={<p>This cannot be undone. Running investigations are skipped.</p>}
        confirmLabel="Delete everything"
        typeToConfirm="delete"
        busy={busy}
        onClose={() => setConfirm("")}
        onConfirm={() => void deleteAll()}
      />
    </div>
  );
}
