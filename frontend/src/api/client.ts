/**
 * The HTTP client.
 *
 * Every failure becomes an `ApiError` carrying the server's `error_code`. The UI branches on
 * the code and never on message text: a component that matches prose breaks the moment the
 * wording improves, and the codes are the part of the contract that is stable.
 */

import type {
  AnalyzeResponse,
  ApiErrorBody,
  FindingTrail,
  KnowledgeGraphView,
  KnowledgeSummary,
  NodeDetail,
  MetricDirections,
  MetricPoint,
  Recording,
  RecordingSummary,
  EventPage,
  FinalReport,
  Finding,
  GapRecord,
  MissionDetail,
  MissionSummary,
  TaskGraphResponse,
} from "./types";
import type { EntityMemory, Episode, Fact, InvestigationMemory, MemoryStatus } from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.error_code;
    this.status = status;
    this.details = body.details ?? {};
  }

  /** The resource exists but the run has not produced it yet, so retrying is the answer. */
  get isNotReady(): boolean {
    return this.code === "MISSION_NOT_FINISHED";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let body: ApiErrorBody;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // A failure that is not even JSON: the server or a proxy died. Synthesise a code so
      // callers still have one to branch on rather than a bare throw.
      body = {
        error_code: "UNREACHABLE",
        message: `the server returned ${response.status}`,
        run_id: null,
        details: {},
      };
    }
    throw new ApiError(response.status, body);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () =>
    request<{ status: string; model: string; provider_healthy: boolean }>("/health"),

  createMission: (objective: string, documents: string[]) =>
    request<MissionDetail>(`${BASE}/missions`, {
      method: "POST",
      body: JSON.stringify({ objective, documents }),
    }),

  listMissions: () => request<MissionSummary[]>(`${BASE}/missions`),

  getMission: (runId: string) => request<MissionDetail>(`${BASE}/missions/${runId}`),

  getTasks: (runId: string) => request<TaskGraphResponse>(`${BASE}/missions/${runId}/tasks`),

  getEvents: (runId: string, offset = 0, limit = 500) =>
    request<EventPage>(`${BASE}/missions/${runId}/events?offset=${offset}&limit=${limit}`),

  getFindings: (runId: string) =>
    request<{ run_id: string; findings: Finding[] }>(`${BASE}/missions/${runId}/findings`),

  getGaps: (runId: string) => request<GapRecord[]>(`${BASE}/missions/${runId}/gaps`),

  getReport: (runId: string) => request<FinalReport>(`${BASE}/missions/${runId}/report`),

  cancelMission: (runId: string) =>
    request<{ run_id: string; cancelling: boolean }>(`${BASE}/missions/${runId}/cancel`, {
      method: "POST",
    }),

  /** The URL an `EventSource` connects to. Streaming is not a fetch. */
  streamUrl: (runId: string) => `${BASE}/missions/${runId}/stream`,

  listRecordings: () => request<RecordingSummary[]>(`${BASE}/recordings`),

  getRecording: (name: string) =>
    request<Recording>(`${BASE}/recordings/${encodeURIComponent(name)}`),

  listEvalReports: () => request<MetricPoint[]>(`${BASE}/evaluation/reports`),

  getMetricDirections: () => request<MetricDirections>(`${BASE}/evaluation/directions`),

  // --- the knowledge layer (Phase 31) -------------------------------------------------------

  getKnowledgeSummary: (runId: string) =>
    request<KnowledgeSummary>(`${BASE}/missions/${runId}/knowledge`),

  getKnowledgeGraph: (runId: string) =>
    request<KnowledgeGraphView>(`${BASE}/missions/${runId}/knowledge/graph`),

  getKnowledgeNode: (runId: string, nodeId: string) =>
    request<NodeDetail>(
      `${BASE}/missions/${runId}/knowledge/nodes/${encodeURIComponent(nodeId)}`,
    ),

  getFindingTrail: (runId: string, findingId: string) =>
    request<FindingTrail>(`${BASE}/missions/${runId}/findings/${findingId}/trail`),

  analyzeDocuments: (documents: string[]) =>
    request<AnalyzeResponse>(`${BASE}/knowledge/analyze`, {
      method: "POST",
      body: JSON.stringify({ documents }),
    }),

  // --- memory (Phase 33) ---
  getMemoryStatus: () => request<MemoryStatus>(`${BASE}/memory`),

  searchEpisodes: (q: string, limit = 20) =>
    request<Episode[]>(`${BASE}/memory/episodes?q=${encodeURIComponent(q)}&limit=${limit}`),

  getInvestigationMemory: (runId: string) =>
    request<InvestigationMemory>(`${BASE}/memory/investigations/${runId}`),

  getFacts: (subject: string, predicate = "") =>
    request<Fact[]>(
      `${BASE}/memory/facts?subject=${encodeURIComponent(subject)}` +
        (predicate ? `&predicate=${encodeURIComponent(predicate)}` : ""),
    ),

  getEntityMemory: (name: string) =>
    request<EntityMemory>(`${BASE}/memory/entities/${encodeURIComponent(name)}`),
};
