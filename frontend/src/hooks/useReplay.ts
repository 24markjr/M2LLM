/**
 * Trace replay — demo insurance, and an honest one.
 *
 * Local inference on laptop hardware stalls sometimes, and a presentation should not depend on a
 * model behaving on the day. A recorded run replays at speed and renders through exactly the
 * same components as a live run, because it returns the same shape (`MissionView`). The page
 * says it is a replay; looking identical is the point, pretending to be live is not.
 *
 * **The snapshot gives the content, the events give the timing.** Event payloads are summaries -
 * a truncated claim, a rounded confidence - so a replay driven by events alone could animate the
 * graph but never drill into a finding's evidence. Instead the recording's snapshot holds the
 * same payloads the live routes serve, and events decide *when* each part of it appears. That is
 * what makes the replay faithful rather than a lesser view wearing the same layout.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type {
  EventRecord,
  Finding,
  GapRecord,
  Recording,
  Stage,
  TaskNode,
  TaskStatus,
} from "../api/types";
import type { MissionView } from "./useMission";
import { STAGE_BY_EVENT } from "./useMission";

export const SPEEDS = [1, 2, 4, 8, 20] as const;
export type Speed = (typeof SPEEDS)[number];

/** Never wait longer than this between two events, whatever the recording says. */
const MAX_GAP_MS = 2500;

export interface ReplayControls {
  recording: Recording | null;
  loading: boolean;
  playing: boolean;
  /** How many events have been emitted so far. */
  position: number;
  total: number;
  speed: Speed;
  elapsedMs: number;
  durationMs: number;
  play: () => void;
  pause: () => void;
  restart: () => void;
  setSpeed: (speed: Speed) => void;
  /** Emit everything at once, for when a demo has run out of time. */
  skipToEnd: () => void;
}

export function useReplay(name: string): MissionView & ReplayControls {
  const [recording, setRecording] = useState<Recording | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(4);

  useEffect(() => {
    setLoading(true);
    setPosition(0);
    api
      .getRecording(name)
      .then((loaded) => {
        setRecording(loaded);
        setError("");
        // Autoplay: a replay opened during a demo should already be moving.
        setPlaying(true);
      })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
      .finally(() => setLoading(false));
  }, [name]);

  const events = recording?.events ?? [];
  const total = events.length;

  // The clock. One timeout per event, scheduled from the real inter-event gap divided by the
  // speed, and capped: a run that genuinely paused 40 seconds waiting for a model should not
  // make a viewer wait 40 seconds to see that it did.
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    if (!playing || position >= total) return;

    const current = events[position];
    const previous = position > 0 ? events[position - 1] : undefined;
    const gap = current && previous ? current.t_offset_ms - previous.t_offset_ms : 0;
    const delay = Math.min(Math.max(gap, 0) / speed, MAX_GAP_MS);

    timer.current = window.setTimeout(() => setPosition((p) => p + 1), delay);

    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [playing, position, total, speed, events]);

  useEffect(() => {
    if (position >= total && total > 0) setPlaying(false);
  }, [position, total]);

  const emitted = useMemo(() => events.slice(0, position), [events, position]);

  const view = useMemo(
    () => reconstruct(recording, emitted, position >= total && total > 0),
    [recording, emitted, position, total],
  );

  return {
    ...view,
    error: error || view.error,
    recording,
    loading,
    playing,
    position,
    total,
    speed,
    elapsedMs: emitted.length > 0 ? (emitted[emitted.length - 1]?.t_offset_ms ?? 0) : 0,
    durationMs: total > 0 ? (events[total - 1]?.t_offset_ms ?? 0) : 0,
    play: useCallback(() => setPlaying(true), []),
    pause: useCallback(() => setPlaying(false), []),
    restart: useCallback(() => {
      setPosition(0);
      setPlaying(true);
    }, []),
    setSpeed: useCallback((next: Speed) => setSpeed(next), []),
    skipToEnd: useCallback(() => {
      setPlaying(false);
      setPosition(total);
    }, [total]),
  };
}

/**
 * Rebuild the view as it stood after the emitted events.
 *
 * Task statuses are driven by events rather than taken from the snapshot, so the graph animates
 * through PENDING -> RUNNING -> COMPLETED exactly as it did live. Findings are revealed as their
 * FINDING_CREATED events arrive, but their *content* comes from the snapshot, so evidence
 * drill-down works on a replay.
 */
function reconstruct(
  recording: Recording | null,
  emitted: EventRecord[],
  finished: boolean,
): MissionView {
  if (recording === null) {
    return {
      mission: null,
      tasks: null,
      findings: [],
      gaps: [],
      report: null,
      events: [],
      liveStage: null,
      streaming: false,
      error: "",
    };
  }

  const snapshot = recording.snapshot;
  const statuses = new Map<string, TaskStatus>();
  const revealedFindings = new Set<string>();
  const revealedGaps = new Set<string>();
  let stage: Stage | null = null;
  let planCreated = false;
  let synthesised = false;

  for (const event of emitted) {
    const nextStage = STAGE_BY_EVENT[event.event_type];
    if (nextStage) stage = nextStage;

    if (event.event_type === "PLAN_CREATED" || event.event_type === "TASK_GRAPH_CREATED") {
      planCreated = true;
    }
    if (event.event_type === "SYNTHESIS_STARTED" || event.event_type === "RUN_COMPLETED") {
      synthesised = true;
    }

    if (event.task_id) {
      const status = TASK_STATUS_BY_EVENT[event.event_type];
      if (status) statuses.set(event.task_id, status);
    }
    if (event.finding_id) revealedFindings.add(event.finding_id);

    if (event.event_type === "EVIDENCE_GAP_DETECTED" || event.event_type === "GAP_DETECTED") {
      const gapId = event.payload["gap_id"];
      if (typeof gapId === "string") revealedGaps.add(gapId);
    }
  }

  const snapshotTasks = snapshot.tasks ?? null;
  const tasks =
    planCreated && snapshotTasks
      ? {
          ...snapshotTasks,
          nodes: snapshotTasks.nodes.map(
            (node): TaskNode => ({
              ...node,
              // Default to PENDING: a task the replay has not reached yet has not run yet, and
              // showing its final status early would give away the ending.
              status: statuses.get(node.task_id) ?? "PENDING",
            }),
          ),
        }
      : null;

  const allFindings: Finding[] = snapshot.findings?.findings ?? [];
  const findings =
    revealedFindings.size > 0
      ? allFindings.filter((f) => revealedFindings.has(f.finding_id))
      : [];

  const allGaps: GapRecord[] = snapshot.gaps ?? [];
  const gaps = revealedGaps.size > 0 ? allGaps.filter((g) => revealedGaps.has(g.gap_id)) : [];

  const mission = snapshot.mission
    ? {
        ...snapshot.mission,
        // Report the run as it stood at this point in the replay, not as it ended.
        status: finished ? snapshot.mission.status : ("RUNNING" as const),
        stage: finished ? ("DONE" as const) : (stage ?? ("UNDERSTANDING" as const)),
        finding_count: findings.length,
      }
    : null;

  return {
    mission,
    tasks,
    findings,
    gaps,
    report: synthesised ? (snapshot.report ?? null) : null,
    events: emitted,
    liveStage: finished ? "DONE" : stage,
    streaming: false,
    error: "",
  };
}

const TASK_STATUS_BY_EVENT: Record<string, TaskStatus> = {
  TASK_READY: "READY",
  TASK_STARTED: "RUNNING",
  TASK_RETRYING: "RUNNING",
  TASK_COMPLETED: "COMPLETED",
  TASK_FAILED: "FAILED",
  TASK_SKIPPED: "SKIPPED",
};
