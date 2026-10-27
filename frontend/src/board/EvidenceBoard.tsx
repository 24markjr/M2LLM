/**
 * The evidence board (Phase U6): the right pane of the investigation workspace.
 *
 * Sources (the text each file was read as, with every cited span marked), the pin board (findings
 * and files joined by the connections the run holds), the timeline, the competing explanations,
 * and the report with its exports. Driven by the same `MissionView` as the journal, so a replay
 * has a board too; what a replay cannot hold says so.
 */

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { api, ApiError } from "../api/client";
import type { Finding, TimelineEvent } from "../api/types";
import type { MissionView } from "../hooks/useMission";
import { Badge, Notice, StatusBadge, Tabs } from "../ui/components";
import { findingStatus } from "../journal/journal";
import {
  initialLayout,
  lineOf,
  marksIn,
  pinsAndStrings,
  segments,
  STRING_LABEL,
  type Point,
} from "./board";
import { ProofPanel } from "./ProofPanel";
import "./board.css";
import { evidenceLabel, SCORE_NOTE } from "../components/confidence";

export type BoardTab = "sources" | "pins" | "timeline" | "hypotheses" | "proof" | "report";

export interface BoardFocus {
  document: string;
  findingId: string;
  /** Changes on every request, so the same citation clicked twice still scrolls to it. */
  nonce: number;
}

const TABS: { id: BoardTab; label: string }[] = [
  { id: "sources", label: "Sources" },
  { id: "pins", label: "Pin board" },
  { id: "timeline", label: "Timeline" },
  { id: "hypotheses", label: "Explanations" },
  { id: "proof", label: "Proof" },
  { id: "report", label: "Report" },
];

const FORMATS = ["pdf", "docx", "md", "json"] as const;

export function EvidenceBoard({
  view,
  runId,
  focus,
  tab,
  onTab,
  wide,
  onWide,
}: {
  view: MissionView;
  runId?: string | undefined;
  focus: BoardFocus | null;
  tab: BoardTab;
  onTab: (tab: BoardTab) => void;
  wide: boolean;
  onWide: (wide: boolean) => void;
}) {
  const { mission, findings } = view;
  const finished = mission ? !["RUNNING", "PENDING"].includes(mission.status) : false;
  const [fetched, setFetched] = useState<Record<string, string> | null>(null);
  const [sourcesError, setSourcesError] = useState("");

  // A replay carries its sources; a live run is asked once it has read its files.
  useEffect(() => {
    if (view.sources !== undefined || !runId || !finished) return;
    let cancelled = false;
    api
      .getSources(runId)
      .then((s) => !cancelled && setFetched(s))
      .catch((exc: unknown) => !cancelled && setSourcesError(exc instanceof ApiError ? exc.message : "The sources could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, [runId, finished, view.sources]);

  const sources = view.sources ?? fetched ?? {};

  return (
    <aside className={`board ${wide ? "wide" : ""}`} aria-label="Evidence board">
      <div className="board-head">
        <Tabs tabs={TABS} active={tab} onChange={(id) => onTab(id as BoardTab)} label="Evidence board" />
        <button
          type="button"
          className="ui-button ghost sm board-expand"
          onClick={() => onWide(!wide)}
          aria-pressed={wide}
          aria-label={wide ? "Side by side with the journal" : "Expand the board"}
          title={wide ? "Side by side with the journal" : "Expand the board"}
        >
          {wide ? "⇥" : "⤢"}
        </button>
      </div>
      <div className="board-body" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "sources" ? (
          <Sources
            sources={sources}
            findings={findings}
            focus={focus}
            note={
              view.sources === null
                ? "This recording was made before runs kept their text, so the files cannot be shown here."
                : sourcesError || (!finished && !view.sources ? "The files appear here once the run has read them." : "")
            }
          />
        ) : null}
        {tab === "pins" ? <PinBoard view={view} runId={runId} sources={sources} wide={wide} /> : null}
        {tab === "timeline" ? <Timeline view={view} runId={runId} finished={finished} /> : null}
        {tab === "hypotheses" ? <Explanations view={view} /> : null}
        {tab === "proof" ? <ProofPanel view={view} runId={runId} finished={finished} /> : null}
        {tab === "report" ? <Report view={view} runId={runId} finished={finished} /> : null}
      </div>
    </aside>
  );
}

// --- sources -----------------------------------------------------------------------------------

function Sources({
  sources,
  findings,
  focus,
  note,
}: {
  sources: Record<string, string>;
  findings: Finding[];
  focus: BoardFocus | null;
  note: string;
}) {
  const names = Object.keys(sources).sort();
  const [open, setOpen] = useState<string>("");
  const [selected, setSelected] = useState<string>("");
  const textRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (!focus) return;
    setOpen(focus.document);
    setSelected(focus.findingId);
  }, [focus]);

  const document = open && open in sources ? open : (names[0] ?? "");
  const text = sources[document] ?? "";
  const marks = useMemo(() => marksIn(document, findings, sources), [document, findings, sources]);
  const pieces = useMemo(() => segments(text, marks), [text, marks]);

  // Bring the focused citation into view once its document is showing.
  useEffect(() => {
    const target = textRef.current?.querySelector<HTMLElement>("mark.on");
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [document, selected, focus?.nonce]);

  if (names.length === 0) {
    return <p className="board-note">{note || "No files were read in this run."}</p>;
  }

  const cited = (name: string) => marksIn(name, findings, sources).length;

  return (
    <div className="board-sources">
      {note ? <Notice tone="info">{note}</Notice> : null}
      <label className="board-field">
        <span>File</span>
        <select value={document} onChange={(e) => setOpen(e.target.value)}>
          {names.map((n) => (
            <option key={n} value={n}>
              {n} ({cited(n)} cited)
            </option>
          ))}
        </select>
      </label>
      <p className="board-note">
        {marks.length
          ? `${marks.length} cited span(s), marked. Select one to see which finding rests on it.`
          : "No finding cites this file."}
      </p>
      <pre className="board-text" ref={textRef}>
        {pieces.map((p, i) =>
          p.findings.length ? (
            <mark
              key={i}
              className={p.findings.includes(selected) ? "on" : ""}
              title={`${p.findings.join(", ")} - line ${lineOf(text, pieces.slice(0, i).reduce((n, s) => n + s.text.length, 0))}`}
              onClick={() => setSelected(p.findings[0] ?? "")}
            >
              {p.text}
            </mark>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </pre>
      {selected ? <SelectedFinding finding={findings.find((f) => f.finding_id === selected)} /> : null}
    </div>
  );
}

function SelectedFinding({ finding }: { finding: Finding | undefined }) {
  if (!finding) return null;
  return (
    <div className="board-selected">
      <StatusBadge status={findingStatus(finding)} />
      <span className="board-id">{finding.finding_id}</span> {finding.claim}
    </div>
  );
}

// --- the pin board -----------------------------------------------------------------------------

const PIN_W = 170;
const PIN_H = 92;

function storageKey(runId: string) {
  return `jarvis.pins.${runId}`;
}

function loadPositions(key: string): Record<string, Point> {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Record<string, Point>) : {};
  } catch {
    return {};
  }
}

function PinBoard({
  view,
  runId,
  sources,
  wide,
}: {
  view: MissionView;
  runId?: string | undefined;
  sources: Record<string, string>;
  wide: boolean;
}) {
  const key = storageKey(runId ?? view.mission?.run_id ?? "replay");
  const { pins, strings } = useMemo(
    () => pinsAndStrings(view.findings, sources, view.hypotheses),
    [view.findings, sources, view.hypotheses],
  );
  const width = wide ? 960 : 400;
  const [moved, setMoved] = useState<Record<string, Point>>(() => loadPositions(key));
  const [active, setActive] = useState<string>("");
  const drag = useRef<{ id: string; dx: number; dy: number } | null>(null);

  const positions = { ...initialLayout(pins, width), ...moved };
  const height = Math.max(320, ...Object.values(positions).map((p) => p.y + PIN_H + 20));

  const save = (next: Record<string, Point>) => {
    setMoved(next);
    try {
      window.localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Positions are a convenience; the board works without them.
    }
  };

  const onDown = (id: string) => (e: ReactPointerEvent<HTMLDivElement>) => {
    const p = positions[id];
    if (!p) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { id, dx: e.clientX - p.x, dy: e.clientY - p.y };
    setActive(id);
  };
  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    setMoved((m) => ({ ...m, [d.id]: { x: Math.max(0, e.clientX - d.dx), y: Math.max(0, e.clientY - d.dy) } }));
  };
  const onUp = () => {
    if (drag.current) save({ ...moved });
    drag.current = null;
  };

  if (pins.length === 0) {
    return <p className="board-note">The pin board fills in as the run makes findings.</p>;
  }

  const touching = new Set(strings.filter((s) => s.from === active || s.to === active).flatMap((s) => [s.from, s.to]));
  const centre = (id: string) => {
    const p = positions[id] ?? { x: 0, y: 0 };
    return { x: p.x + PIN_W / 2, y: p.y + PIN_H / 2 };
  };
  const byFinding = new Map(view.findings.map((f) => [f.finding_id, f]));
  const nameOf = (id: string) => (id.startsWith("doc:") ? id.slice(4) : id);

  return (
    <div className="pins">
      <div className="pins-legend">
        {(["same-line", "contradiction", "same-explanation", "cites"] as const).map((k) => (
          <span key={k} className={`pins-key ${k}`}>
            {STRING_LABEL[k]}
          </span>
        ))}
        <button type="button" className="ui-button ghost sm" onClick={() => save({})}>
          Tidy up
        </button>
      </div>
      <p className="board-note">
        Drag the pins; select one to light up its strings. Strings are only the connections the run holds.
      </p>
      <div className="pins-canvas" style={{ height }} onPointerMove={onMove} onPointerUp={onUp}>
        <svg className="pins-strings" width="100%" height={height} aria-hidden="true">
          {strings.map((s) => {
            const a = centre(s.from);
            const b = centre(s.to);
            const lit = active && (s.from === active || s.to === active);
            return (
              <line
                key={`${s.from}|${s.to}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className={`string ${s.kind} ${lit ? "lit" : active ? "dim" : ""}`}
              >
                <title>{s.why}</title>
              </line>
            );
          })}
        </svg>
        {pins.map((p) => {
          const pos = positions[p.id] ?? { x: 0, y: 0 };
          const f = byFinding.get(p.id);
          return (
            <div
              key={p.id}
              className={`pin ${p.kind} ${active === p.id ? "active" : ""} ${active && !touching.has(p.id) && active !== p.id ? "dim" : ""}`}
              style={{ left: pos.x, top: pos.y, width: PIN_W, height: PIN_H }}
              onPointerDown={onDown(p.id)}
              role="button"
              tabIndex={0}
              aria-label={`${p.kind === "finding" ? p.id : "File"}: ${p.label}`}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setActive(active === p.id ? "" : p.id)}
            >
              <div className="pin-top">
                {f ? <StatusBadge status={findingStatus(f)} /> : <Badge>file</Badge>}
                <span className="pin-detail" title={p.detail}>{f ? p.id : p.detail}</span>
              </div>
              <div className="pin-label">{p.label}</div>
            </div>
          );
        })}
      </div>
      {active ? (
        <ul className="pins-why">
          {strings
            .filter((s) => s.from === active || s.to === active)
            .map((s) => (
              <li key={`${s.from}|${s.to}`}>
                <span className={`pins-key ${s.kind}`}>{STRING_LABEL[s.kind]}</span> {nameOf(s.from === active ? s.to : s.from)}: {s.why}
              </li>
            ))}
        </ul>
      ) : null}
    </div>
  );
}

// --- timeline ----------------------------------------------------------------------------------

function dateLabel(e: TimelineEvent): string {
  if (!e.date) return "undated";
  const { year, month, day } = e.date;
  const parts = [day, month || null, year].filter((x) => x !== null && x !== 0);
  return `${parts.join("/")}${e.year_inferred ? " (year inferred)" : ""}`;
}

function Timeline({ view, runId, finished }: { view: MissionView; runId?: string | undefined; finished: boolean }) {
  const [fetched, setFetched] = useState<TimelineEvent[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (view.timeline !== undefined || !runId || !finished) return;
    let cancelled = false;
    api
      .getTimeline(runId)
      .then((t) => !cancelled && setFetched(t))
      .catch((exc: unknown) => !cancelled && setError(exc instanceof ApiError ? exc.message : "The timeline could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, [runId, finished, view.timeline]);

  const events = view.timeline ?? fetched;
  if (error) return <Notice tone="info">{error}</Notice>;
  if (!events) return <p className="board-note">{finished ? "Loading the timeline." : "The timeline is built once the run finishes."}</p>;
  if (events.length === 0) return <p className="board-note">No dated statements were found in the files.</p>;
  return (
    <ol className="board-timeline">
      {events.map((e) => (
        <li key={e.claim_id}>
          <span className="board-when">{dateLabel(e)}</span>
          <span>
            <strong>{e.entity_name}</strong> {e.attribute.replace(/_/g, " ")}: {e.value}
          </span>
          <span className="board-src">{e.source}</span>
        </li>
      ))}
    </ol>
  );
}

// --- competing explanations --------------------------------------------------------------------

function Explanations({ view }: { view: MissionView }) {
  const set = view.hypotheses;
  if (!set) return <p className="board-note">Competing explanations are weighed once the findings are checked.</p>;
  if (set.hypotheses.length === 0) return <p className="board-note">{set.skipped_reason || "No competing explanations were needed."}</p>;
  return (
    <div className="board-hyps">
      {set.summary ? <p>{set.summary}</p> : null}
      {set.hypotheses.map((h) => (
        <div key={h.hypothesis_id} className="board-hyp">
          <div>
            <Badge tone={h.status === "SUPPORTED" ? "verified" : h.status === "REJECTED" ? "unsupported" : "unknown"}>
              {h.status.toLowerCase().replace(/_/g, " ")}
            </Badge>{" "}
            {h.statement}
          </div>
          <div className="board-note">
            For: {h.supporting.map((r) => r.finding_id).join(", ") || "none"} · Against:{" "}
            {h.contradicting.map((r) => r.finding_id).join(", ") || "none"}
          </div>
          {h.next_evidence ? <div className="board-note">Next evidence: {h.next_evidence.text}</div> : null}
        </div>
      ))}
    </div>
  );
}

// --- report ------------------------------------------------------------------------------------

function Report({ view, runId, finished }: { view: MissionView; runId?: string | undefined; finished: boolean }) {
  const { mission, report } = view;
  return (
    <div className="board-report">
      {report ? (
        <p>
          {report.verified_findings.length} verified, {report.uncertain_findings.length} uncertain,{" "}
          {report.rejected_findings.length} rejected; {report.unresolved_gaps.length} gap(s) open. Overall:{" "}
          <span title={`${report.overall_confidence.toFixed(2)}. ${SCORE_NOTE}`}>{evidenceLabel(report.overall_confidence)}</span>.
        </p>
      ) : (
        <p className="board-note">The report is written once every finding is checked.</p>
      )}
      {runId && finished ? (
        <>
          <h4>Export</h4>
          <div className="board-links">
            {FORMATS.map((f) => (
              <a key={f} className="ui-button ghost sm" href={api.investigationReportUrl(runId, f)} download>
                {f.toUpperCase()}
              </a>
            ))}
          </div>
          <h4>Open</h4>
          <div className="board-links">
            {mission?.knowledge_store ? (
              <a className="ui-button ghost sm" href={`#/mission/${runId}/graph`}>
                Knowledge graph
              </a>
            ) : null}
            <a className="ui-button ghost sm" href={`#/mission/${runId}/attack`}>
              Attack path
            </a>
            <a className="ui-button ghost sm" href={`#/mission/${runId}/details`}>
              All details
            </a>
          </div>
        </>
      ) : (
        <p className="board-note">{runId ? "Exports are ready when the run finishes." : "Exports come from a live run, not a replay."}</p>
      )}
    </div>
  );
}
