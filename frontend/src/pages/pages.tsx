/**
 * The three views.
 *
 * The landing view is a mission list plus "New mission" - never a chat transcript. This is an
 * operations console: the unit of work is a run with a plan, a trace and a report, not a turn
 * in a conversation.
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { MissionDetail, MissionSummary, RecordingSummary } from "../api/types";
import {
  EventTimeline,
  ExecutionStats,
  Findings,
  Gaps,
  PhaseTracker,
  Report,
  TaskGraph,
} from "../components/mission";
import type { MissionView } from "../hooks/useMission";
import { useMission, useMissionList } from "../hooks/useMission";
import { SPEEDS, useReplay } from "../hooks/useReplay";
import { EvaluationDashboard } from "../components/evaluation";

/** Fixtures that ship with the repo, offered so a demo needs no upload. */
const SUGGESTED = [
  "aurora_project_report.txt",
  "aurora_financial_report.txt",
  "aurora_budget.csv",
];

const SUGGESTED_OBJECTIVE =
  "Investigate the Aurora project reports and identify any contradictions between the " +
  "timeline and the financial information.";

export function MissionList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { missions, loading, error, reload } = useMissionList();

  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <button className="primary" onClick={onNew}>
          New mission
        </button>
        <button onClick={reload}>Refresh</button>
        <span className="spacer" />
        <span className="dim mono">{missions.length} missions</span>
      </div>

      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>Missions</h2>
        {loading ? (
          <div className="empty">Loading.</div>
        ) : missions.length === 0 ? (
          <div className="empty">
            No missions yet. Start one - the Aurora fixtures are prefilled.
          </div>
        ) : (
          missions.map((mission) => (
            <MissionRow key={mission.run_id} mission={mission} onOpen={onOpen} />
          ))
        )}
      </div>
    </>
  );
}

function MissionRow({
  mission,
  onOpen,
}: {
  mission: MissionSummary;
  onOpen: (id: string) => void;
}) {
  return (
    <a
      className="mission-row"
      href={`#/mission/${mission.run_id}`}
      onClick={(event) => {
        event.preventDefault();
        onOpen(mission.run_id);
      }}
    >
      <div className="line1">
        <span className="objective">{mission.objective}</span>
        <span className={`status ${mission.status.toLowerCase()}`}>
          {mission.status === "RUNNING" ? mission.stage : mission.status}
        </span>
      </div>
      <div className="meta">
        <span>{mission.run_id}</span>
        <span>
          {mission.finding_count} finding{mission.finding_count === 1 ? "" : "s"}
          {mission.finding_count > 0 ? ` (${mission.verified_count} verified)` : ""}
        </span>
        {mission.unresolved_gap_count > 0 ? (
          <span>{mission.unresolved_gap_count} open gaps</span>
        ) : null}
        <span>{mission.documents.length} documents</span>
        <span>{new Date(mission.created_at).toLocaleString()}</span>
      </div>
    </a>
  );
}

export function NewMission({
  onStarted,
  onCancel,
}: {
  onStarted: (mission: MissionDetail) => void;
  onCancel: () => void;
}) {
  const [objective, setObjective] = useState(SUGGESTED_OBJECTIVE);
  const [documents, setDocuments] = useState<string[]>(SUGGESTED);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const start = () => {
    setBusy(true);
    setError("");
    api
      .createMission(objective.trim(), documents)
      .then(onStarted)
      .catch((exc: unknown) => {
        // Codes, not prose. Each of these is a distinct thing for the user to do next.
        if (exc instanceof ApiError) {
          if (exc.code === "AT_CAPACITY") {
            setError("The engine is already running as many missions as it allows. Wait for one to finish.");
          } else if (exc.code === "NO_READABLE_DOCUMENTS") {
            setError("None of those documents could be read. Check the names against .agent/fixtures/.");
          } else if (exc.code === "UNREACHABLE") {
            setError("Cannot reach the engine. Start it with: uvicorn app.api.app:create_app --factory");
          } else {
            setError(`${exc.code}: ${exc.message}`);
          }
        } else {
          setError(String(exc));
        }
        setBusy(false);
      });
  };

  const toggle = (name: string) =>
    setDocuments((current) =>
      current.includes(name) ? current.filter((d) => d !== name) : [...current, name],
    );

  return (
    <>
      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>New mission</h2>
        <div className="panel-body">
          <div className="field">
            <label htmlFor="objective">Objective</label>
            <textarea
              id="objective"
              rows={3}
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              placeholder="What should be investigated?"
            />
            <div className="hint">
              State a question, not a task list. An objective too vague to plan against comes
              back as a clarification request rather than a guessed plan.
            </div>
          </div>

          <div className="field">
            <label>Documents</label>
            <div className="row">
              {SUGGESTED.map((name) => (
                <button
                  key={name}
                  className={documents.includes(name) ? "primary" : ""}
                  onClick={() => toggle(name)}
                >
                  {documents.includes(name) ? "✓ " : ""}
                  {name}
                </button>
              ))}
            </div>
            <div className="hint">
              Resolved by name inside <code className="mono">.agent/fixtures/</code>. Anything
              unreadable is excluded and reported rather than silently skipped.
            </div>
          </div>

          <div className="row">
            <button
              className="primary"
              onClick={start}
              disabled={busy || objective.trim().length < 8}
            >
              {busy ? "Starting." : "Start mission"}
            </button>
            <button onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export function MissionDetailPage({ runId, onBack }: { runId: string; onBack: () => void }) {
  const live = useMission(runId);
  const { mission, streaming } = live;
  const done = isFinished(mission);

  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <button onClick={onBack}>&larr; Missions</button>
        <span className="spacer" />
        {mission && !done ? (
          <button className="danger" onClick={live.cancel}>
            Cancel run
          </button>
        ) : null}
        <span className="dim mono">
          {streaming ? "● streaming" : done ? "run finished" : "not streaming"}
        </span>
      </div>

      <MissionViewPanels view={live} />
    </>
  );
}

export function isFinished(mission: MissionDetail | null): boolean {
  return (
    mission !== null &&
    ["COMPLETED", "FAILED", "CANCELLED", "CLARIFICATION_NEEDED"].includes(mission.status)
  );
}

/**
 * Every panel of a mission, driven by a `MissionView`.
 *
 * Shared by the live page and the replay page. Both pass the same shape, so a recorded run is
 * rendered by the same code that renders a live one - which is what lets the replay be called
 * faithful rather than merely similar. A separate replay view would drift, and a replay that
 * looks *nearly* right is worse than one that obviously does not: it invites a viewer to trust
 * a rendering no live run ever produced.
 */
export function MissionViewPanels({ view }: { view: MissionView }) {
  const { mission } = view;
  const done = isFinished(mission);

  return (
    <>
      {view.error ? <div className="notice error">{view.error}</div> : null}

      {mission ? (
        <>
          <div className="panel">
            <h2>
              Objective
              <span className="count">{mission.run_id}</span>
            </h2>
            <div className="panel-body">
              <div style={{ marginBottom: 10 }}>{mission.objective}</div>
              <div className="meta mono dim">
                {mission.goal ? <>goal: {mission.goal} &middot; </> : null}
                status: {mission.status}
                {mission.termination_reason ? (
                  <> &middot; terminated: {mission.termination_reason}</>
                ) : null}
                {mission.replan_iterations > 0 ? (
                  <> &middot; {mission.replan_iterations} replan iteration(s)</>
                ) : null}
              </div>
              {mission.required_operations.length > 0 ? (
                <div className="hint mono">
                  operations: {mission.required_operations.join(", ")}
                </div>
              ) : null}
            </div>
          </div>

          {/* A clarification request is an outcome, not an error. The engine refused to plan
              on a guess, and the question it needs answered is the result. */}
          {mission.status === "CLARIFICATION_NEEDED" ? (
            <div className="notice warn">
              <strong>Clarification needed.</strong> {mission.clarification_question}
              <div className="hint">
                Planning stopped deliberately. A plan built on a guessed objective looks
                exactly like one built on an understanding.
              </div>
            </div>
          ) : null}

          {mission.status === "FAILED" ? (
            <div className="notice error">
              <strong>
                <code>{mission.error_code || "FAILED"}</code>
              </strong>{" "}
              {mission.error_message}
            </div>
          ) : null}

          <PhaseTracker stage={view.liveStage ?? mission.stage} done={done} />
          <TaskGraph graph={view.tasks} />
          <Findings findings={view.findings} gaps={view.gaps} tasks={view.tasks} />
          <Gaps gaps={view.gaps} />
          <Report report={view.report} />
          <ExecutionStats report={view.report} />
          <EventTimeline events={view.events} />
        </>
      ) : (
        <div className="panel">
          <div className="empty">Loading mission.</div>
        </div>
      )}
    </>
  );
}

/**
 * Replay a recorded run.
 *
 * Disclosed, always. Looking identical to a live run is the point; being mistaken for one is not,
 * so the banner stays for the whole replay rather than appearing once and fading.
 */
export function ReplayPage({ onBack }: { onBack: () => void }) {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listRecordings()
      .then((rows) => {
        setRecordings(rows);
        const first = rows[0];
        if (first) setSelected(first.file);
      })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, []);

  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <button onClick={onBack}>&larr; Missions</button>
        <span className="spacer" />
        <span className="dim mono">{recordings.length} recordings</span>
      </div>

      {error ? <div className="notice error">{error}</div> : null}

      <div className="panel">
        <h2>
          Recorded runs
          <span className="count">replayed at speed, never re-executed</span>
        </h2>
        {recordings.length === 0 ? (
          <div className="empty">
            No recordings yet. Every mission started through the API records itself to{" "}
            <code className="mono">.agent/traces/</code>.
          </div>
        ) : (
          <div className="panel-body">
            <div className="row">
              {recordings.map((recording) => (
                <button
                  key={recording.file}
                  className={selected === recording.file ? "primary" : ""}
                  onClick={() => setSelected(recording.file)}
                  title={recording.objective}
                >
                  {recording.run_id} &middot; {recording.event_count} events &middot;{" "}
                  {Math.round(recording.duration_ms / 1000)}s
                  {recording.committed ? " · committed" : ""}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {selected ? <Replay key={selected} name={selected} /> : null}
    </>
  );
}

function Replay({ name }: { name: string }) {
  const replay = useReplay(name);

  if (replay.loading) {
    return (
      <div className="panel">
        <div className="empty">Loading recording.</div>
      </div>
    );
  }

  const progress = replay.total > 0 ? (replay.position / replay.total) * 100 : 0;
  const atEnd = replay.position >= replay.total;

  return (
    <>
      {/* Not dismissible, and not a toast. A viewer who looks away and back must still be able
          to tell that this is a recording. */}
      <div className="replay-banner">
        <strong>REPLAY</strong>
        <span>
          recorded{" "}
          {replay.recording ? new Date(replay.recording.recorded_at).toLocaleString() : ""}
          {replay.recording?.model ? ` on ${replay.recording.model}` : ""} &middot; nothing is
          being executed now
        </span>
      </div>

      <div className="panel">
        <div className="replay-controls">
          {replay.playing ? (
            <button onClick={replay.pause}>&#10073;&#10073; Pause</button>
          ) : (
            <button className="primary" onClick={replay.play} disabled={atEnd}>
              &#9654; Play
            </button>
          )}
          <button onClick={replay.restart}>&#8635; Restart</button>
          <button onClick={replay.skipToEnd} disabled={atEnd}>
            Skip to end
          </button>

          <span className="dim">speed</span>
          {SPEEDS.map((speed) => (
            <button
              key={speed}
              className={replay.speed === speed ? "primary" : ""}
              onClick={() => replay.setSpeed(speed)}
            >
              {speed}x
            </button>
          ))}

          <span className="spacer" />
          <span className="mono dim">
            {replay.position}/{replay.total} events &middot;{" "}
            {(replay.elapsedMs / 1000).toFixed(1)}s of {(replay.durationMs / 1000).toFixed(1)}s
          </span>
        </div>
        <div className="replay-progress">
          <i style={{ width: `${progress}%` }} />
        </div>
      </div>

      <MissionViewPanels view={replay} />
    </>
  );
}

export function EvaluationPage({ onBack }: { onBack: () => void }) {
  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <button onClick={onBack}>&larr; Missions</button>
        <span className="spacer" />
        <span className="dim mono">every figure computed by a run</span>
      </div>
      <EvaluationDashboard />
    </>
  );
}
