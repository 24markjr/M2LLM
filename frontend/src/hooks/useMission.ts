/**
 * Data hooks.
 *
 * The live channel is `EventSource`, not polling. The browser handles reconnection and sends
 * `Last-Event-ID` itself, which is the whole reason the API chose SSE (ADR-008) - so the one
 * thing this file must not do is reimplement that.
 *
 * When the stream closes, the hooks refetch the mission's settled state. The stream says what
 * happened; the REST endpoints say what is true now, and a UI built only on the stream would
 * have to reconstruct state from events it might have joined late.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type {
  EventRecord,
  FinalReport,
  Finding,
  GapRecord,
  MissionDetail,
  MissionSummary,
  Stage,
  TaskGraphResponse,
} from "../api/types";

/**
 * Events that mark a phase boundary, mirroring `PHASE_EVENTS` in the backend.
 *
 * Exported because replay reconstructs the same stage progression from the same events. Two
 * copies of this map would let a replayed run show a different phase to the live run it records.
 */
export const STAGE_BY_EVENT: Record<string, Stage> = {
  INTENT_CREATED: "PLANNING",
  PLAN_CREATED: "PLANNING",
  TASK_GRAPH_CREATED: "EXECUTING",
  REASONING_STARTED: "REASONING",
  VERIFICATION_STARTED: "VERIFYING",
  REPLAN_STARTED: "REPLANNING",
  SYNTHESIS_STARTED: "SYNTHESIZING",
  RUN_COMPLETED: "DONE",
  RUN_FAILED: "DONE",
};

export function useMissionList(): {
  missions: MissionSummary[];
  loading: boolean;
  error: string;
  reload: () => void;
} {
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    setLoading(true);
    api
      .listMissions()
      .then((rows) => {
        setMissions(rows);
        setError("");
      })
      .catch((exc: unknown) => setError(describe(exc)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  return { missions, loading, error, reload };
}

/**
 * Everything a mission view needs, whether it came from a live run or a recording.
 *
 * Shared on purpose: `useMission` and `useReplay` both return this, so the detail page renders a
 * replay through exactly the same components as a live run. A separate replay view would drift,
 * and a replay that looks *nearly* like the real thing is worse than one that obviously does not.
 */
export interface MissionView {
  mission: MissionDetail | null;
  tasks: TaskGraphResponse | null;
  findings: Finding[];
  gaps: GapRecord[];
  report: FinalReport | null;
  events: EventRecord[];
  /** Derived from the stream, so the tracker moves before any request returns. */
  liveStage: Stage | null;
  streaming: boolean;
  error: string;
}

export interface LiveMission extends MissionView {
  cancel: () => void;
}

export function useMission(runId: string): LiveMission {
  const [mission, setMission] = useState<MissionDetail | null>(null);
  const [tasks, setTasks] = useState<TaskGraphResponse | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [gaps, setGaps] = useState<GapRecord[]>([]);
  const [report, setReport] = useState<FinalReport | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [liveStage, setLiveStage] = useState<Stage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const detail = await api.getMission(runId);
      setMission(detail);

      // Each of these can legitimately not exist yet. A 409 means "not finished", which is
      // not an error to show the user - it is the run still working.
      const [taskResult, findingResult, gapResult] = await Promise.allSettled([
        api.getTasks(runId),
        api.getFindings(runId),
        api.getGaps(runId),
      ]);
      if (taskResult.status === "fulfilled") setTasks(taskResult.value);
      if (findingResult.status === "fulfilled") setFindings(findingResult.value.findings);
      if (gapResult.status === "fulfilled") setGaps(gapResult.value);

      if (detail.has_report) {
        setReport(await api.getReport(runId));
      }
      setError("");
    } catch (exc: unknown) {
      if (exc instanceof ApiError && exc.isNotReady) return;
      setError(describe(exc));
    }
  }, [runId]);

  // The live stream. One EventSource per mission, closed on unmount so a navigation does not
  // leave a subscriber attached to a finished run.
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    void refresh();

    const source = new EventSource(api.streamUrl(runId));
    sourceRef.current = source;
    setStreaming(true);

    source.onmessage = (message: MessageEvent<string>) => {
      // Unnamed frames only; every real event arrives under its own `event:` name and is
      // handled by the listener below.
      void message;
    };

    const onEvent = (message: MessageEvent<string>) => {
      let record: EventRecord;
      try {
        record = JSON.parse(message.data) as EventRecord;
      } catch {
        return;
      }
      setEvents((previous) => [...previous, record]);

      const stage = STAGE_BY_EVENT[record.event_type];
      if (stage) setLiveStage(stage);

      // A finding appearing is worth a refetch: the claim, its evidence and its verification
      // state arrive together from the REST endpoint, and showing a claim before its
      // verification state is a claim overstated.
      if (record.event_type === "FINDING_VERIFIED" || record.event_type === "FINDING_REJECTED") {
        void refresh();
      }
    };

    // Named listeners for the event kinds the UI reacts to, plus a catch-all via `message`
    // is not enough on its own - SSE delivers named events only to named listeners.
    const kinds = [
      "RUN_STARTED",
      "INTENT_CREATED",
      "PLAN_CREATED",
      "TASK_GRAPH_CREATED",
      "TOOL_SELECTED",
      "TASK_STARTED",
      "TASK_COMPLETED",
      "TASK_FAILED",
      "OBSERVATION_RECORDED",
      "REASONING_STARTED",
      "FINDING_CREATED",
      "FINDING_DISCARDED",
      "VERIFICATION_STARTED",
      "FINDING_VERIFIED",
      "FINDING_REJECTED",
      "GAP_DETECTED",
      "REPLAN_STARTED",
      "PLAN_REVISED",
      "SYNTHESIS_STARTED",
      "LLM_CALL_COMPLETED",
      "RUN_COMPLETED",
      "RUN_FAILED",
    ];
    for (const kind of kinds) source.addEventListener(kind, onEvent as EventListener);

    source.addEventListener("stream_closed", () => {
      // The run is over. Close explicitly, or the browser reconnects to a mission that will
      // never emit again.
      source.close();
      setStreaming(false);
      void refresh();
    });

    source.onerror = () => {
      // Do not close here. An error is usually a dropped connection, and the browser will
      // reconnect with Last-Event-ID - closing would throw away the guarantee the API went
      // to some trouble to provide.
      setStreaming(false);
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [runId, refresh]);

  const cancel = useCallback(() => {
    api
      .cancelMission(runId)
      .then(() => refresh())
      .catch((exc: unknown) => setError(describe(exc)));
  }, [runId, refresh]);

  return {
    mission,
    tasks,
    findings,
    gaps,
    report,
    events,
    liveStage,
    streaming,
    error,
    cancel,
  };
}

/** Turn any thrown value into something renderable, preferring the server's code. */
function describe(exc: unknown): string {
  if (exc instanceof ApiError) {
    return exc.code === "UNREACHABLE"
      ? "Cannot reach the engine. Is the API running on port 8000?"
      : `${exc.code}: ${exc.message}`;
  }
  return exc instanceof Error ? exc.message : String(exc);
}
