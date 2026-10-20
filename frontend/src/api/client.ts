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
  FindingChain,
  GapRecord,
  MissionDetail,
  MissionSummary,
  TaskGraphResponse,
} from "./types";
import type { EntityMemory, Episode, Fact, InvestigationMemory, MemoryStatus } from "./types";
import type { ClaimComparison, ClaimConflict, EntityInvestigation, SearchHit, TimelineEvent } from "./types";
import type { FormatSpec, StoredDocument, UploadedDocument } from "./types";
import type { RetrieveResponse, WorkspaceView } from "./types";
import type { AuthorityTier, EvidenceDetail, EvidenceItem, EvidenceList, IntegrityCheck } from "./types";
import type { Case, CaseDetail, CaseList, CaseSeverity, CaseStatus } from "./types";
import type { ChallengeResult, HypothesisSet, PlanTree } from "./types";
import type { AuditEntry, ReviewList, ReviewResponse, ReviewState } from "./types";
import type { InvestigationReport } from "./types";
import type { CyberAnalysis } from "./types";
import type { QualitySummary } from "./types";
import type { StoreStatus } from "./types";
import type { DeletionReport } from "./types";
import type { BenchmarkReport, Comparison, Receipt } from "./types";
import { DemoError, STATIC_DEMO, demoRequest } from "./demo";

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
  // The GitHub Pages build has no API: committed recordings are served as static files.
  if (STATIC_DEMO) {
    try {
      return await demoRequest<T>(path, init);
    } catch (error) {
      if (error instanceof DemoError) throw new ApiError(503, error.body);
      throw error;
    }
  }

  // A file upload sends FormData, whose content type (with its boundary) the browser must set.
  const isForm = init?.body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(init?.headers ?? {}) },
    });
  } catch {
    // No answer at all: the API is not running. Say so, rather than the browser's "Failed to fetch".
    throw new ApiError(0, {
      error_code: "UNREACHABLE",
      message: "The JARVIS engine is not running. Start it with scripts\\start-jarvis.ps1, then reload this page.",
      run_id: null,
      details: {},
    });
  }

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

  // A deletion answers 204 with no body (Phase U1).
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () =>
    request<{ status: string; model: string; provider_healthy: boolean }>("/health"),

  /** `workspaceId` (Phase 40): the mission's documents are ingested there and searched by meaning. */
  /** `mode` (Phase U4): makes the mode's operations required in the plan. */
  createMission: (
    objective: string,
    documents: string[],
    workspaceId?: string,
    caseId?: string,
    mode: "investigate" | "compare" | "timeline" | "security" = "investigate",
  ) =>
    request<MissionDetail>(`${BASE}/missions`, {
      method: "POST",
      body: JSON.stringify({
        objective,
        documents,
        mode,
        ...(workspaceId ? { workspace_id: workspaceId } : {}),
        ...(caseId ? { case_id: caseId } : {}),
      }),
    }),

  listMissions: () => request<MissionSummary[]>(`${BASE}/missions`),

  getMission: (runId: string) => request<MissionDetail>(`${BASE}/missions/${runId}`),

  getTasks: (runId: string) => request<TaskGraphResponse>(`${BASE}/missions/${runId}/tasks`),

  getEvents: (runId: string, offset = 0, limit = 500) =>
    request<EventPage>(`${BASE}/missions/${runId}/events?offset=${offset}&limit=${limit}`),

  getFindings: (runId: string) =>
    request<{ run_id: string; findings: Finding[]; why?: Record<string, string[]> }>(
      `${BASE}/missions/${runId}/findings`,
    ),

  /** Challenge one finding: counter-evidence, its own lines, the verifier, authority (Phase 48). */
  challengeFinding: (runId: string, findingId: string) =>
    request<ChallengeResult>(`${BASE}/missions/${runId}/findings/${findingId}/challenge`, {
      method: "POST",
    }),

  getChallenges: (runId: string) => request<ChallengeResult[]>(`${BASE}/missions/${runId}/challenges`),

  /** Which findings need review, why, their state and every decision (Phase 50). */
  getReviews: (runId: string) => request<ReviewList>(`${BASE}/missions/${runId}/reviews`),

  reviewFinding: (
    runId: string,
    findingId: string,
    body: { state: ReviewState; reason?: string; modified_claim?: string; replan?: boolean },
  ) =>
    request<ReviewResponse>(`${BASE}/missions/${runId}/findings/${findingId}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** The investigation report as it stands (Phase 51). */
  getInvestigationReport: (runId: string) =>
    request<InvestigationReport>(`${BASE}/missions/${runId}/investigation-report`),

  /** A download of the report; recorded in custody and the audit log. */
  investigationReportUrl: (runId: string, fmt: string) =>
    `${BASE}/missions/${runId}/investigation-report/export/${fmt}`,

  /** The store behind cases, evidence, the audit log and investigations (Phase U1). */
  getStores: () => request<{ stores: StoreStatus[] }>(`${BASE}/system/stores`),

  /** The audit log, newest first (Phase 50). */
  getAudit: (target = "", limit = 200) =>
    request<AuditEntry[]>(`${BASE}/audit?limit=${limit}${target ? `&target=${encodeURIComponent(target)}` : ""}`),

  /** The plan tree: workstreams, steps with their why, and every change (Phase 49). */
  getPlan: (runId: string) => request<PlanTree>(`${BASE}/missions/${runId}/plan`),

  /** Competing explanations ranked by computed support (Phase 47). */
  getHypotheses: (runId: string) => request<HypothesisSet>(`${BASE}/missions/${runId}/hypotheses`),

  /** How a finding came to be: claim, evidence, extraction, reasoning, verification, conclusion. */
  getFindingChain: (runId: string, findingId: string) =>
    request<FindingChain>(`${BASE}/missions/${runId}/findings/${findingId}/chain`),

  getGaps: (runId: string) => request<GapRecord[]>(`${BASE}/missions/${runId}/gaps`),

  getReport: (runId: string) => request<FinalReport>(`${BASE}/missions/${runId}/report`),

  /** The verification receipt (U7). */
  getReceipt: (runId: string) => request<Receipt>(`${BASE}/missions/${runId}/receipt`),

  /** The plain-model comparison (U7): COMPARISON_NOT_RUN until it is asked for with `runComparison`. */
  getComparison: (runId: string) => request<Comparison>(`${BASE}/missions/${runId}/comparison`),
  runComparison: (runId: string) => request<Comparison>(`${BASE}/missions/${runId}/comparison`, { method: "POST" }),

  /** The text each file was read as, by document (U6): the evidence board's viewer. */
  getSources: (runId: string) => request<Record<string, string>>(`${BASE}/missions/${runId}/sources`),

  cancelMission: (runId: string) =>
    request<{ run_id: string; cancelling: boolean }>(`${BASE}/missions/${runId}/cancel`, {
      method: "POST",
    }),

  /** The URL an `EventSource` connects to. Streaming is not a fetch. */
  streamUrl: (runId: string) => `${BASE}/missions/${runId}/stream`,

  /** Recordings as records (U1); failed runs with no findings and second copies only with `includeHidden`. */
  listRecordings: (includeHidden = false) =>
    request<RecordingSummary[]>(`${BASE}/recordings${includeHidden ? "?include_hidden=true" : ""}`),

  /** Delete one local recording; a committed one answers RECORDING_KEPT (U1). */
  deleteRecording: (file: string) =>
    request<void>(`${BASE}/recordings/${encodeURIComponent(file)}`, { method: "DELETE" }),

  /** Delete the hidden recordings, or all local ones (U1). */
  deleteRecordings: (scope: "hidden" | "all") =>
    request<{ deleted: number; kept: number }>(`${BASE}/recordings?scope=${scope}&confirm=delete`, { method: "DELETE" }),

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

  // --- Member 3's investigation views (Phase 36) ---
  searchKnowledge: (runId: string, q: string, depth = 1) =>
    request<SearchHit[]>(
      `${BASE}/missions/${runId}/knowledge/search?q=${encodeURIComponent(q)}&depth=${depth}`,
    ),

  getTimeline: (runId: string, entityId?: string) =>
    request<TimelineEvent[]>(
      `${BASE}/missions/${runId}/knowledge/timeline` +
        (entityId ? `?entity_id=${encodeURIComponent(entityId)}` : ""),
    ),

  compareClaims: (runId: string, claimA: string, claimB: string) =>
    request<ClaimComparison>(
      `${BASE}/missions/${runId}/knowledge/timeline/compare?claim_a=${encodeURIComponent(claimA)}` +
        `&claim_b=${encodeURIComponent(claimB)}`,
    ),

  getConflicts: (runId: string, entityId?: string) =>
    request<ClaimConflict[]>(
      `${BASE}/missions/${runId}/knowledge/conflicts` +
        (entityId ? `?entity_id=${encodeURIComponent(entityId)}` : ""),
    ),

  investigate: (runId: string, name: string) =>
    request<EntityInvestigation>(
      `${BASE}/missions/${runId}/knowledge/investigation?name=${encodeURIComponent(name)}`,
    ),

  getFindingTrail: (runId: string, findingId: string) =>
    request<FindingTrail>(`${BASE}/missions/${runId}/findings/${findingId}/trail`),

  analyzeDocuments: (documents: string[]) =>
    request<AnalyzeResponse>(`${BASE}/knowledge/analyze`, {
      method: "POST",
      body: JSON.stringify({ documents }),
    }),

  // --- documents (Phase 38) ---
  getFormats: () => request<FormatSpec[]>(`${BASE}/documents/formats`),

  listUploads: () => request<StoredDocument[]>(`${BASE}/documents`),

  uploadDocuments: (files: File[], workspace?: string, caseId?: string) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    const params = [
      workspace ? `workspace=${encodeURIComponent(workspace)}` : "",
      caseId ? `case=${encodeURIComponent(caseId)}` : "",
    ].filter(Boolean);
    const query = params.length ? `?${params.join("&")}` : "";
    return request<UploadedDocument[]>(`${BASE}/documents${query}`, { method: "POST", body: form });
  },

  // --- cases (Phase 44) ---
  /** Cases, pinned first; `q` searches ids, titles, descriptions and the questions asked (U1). */
  listCases: (q = "") => request<CaseList>(`${BASE}/cases${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  /** Delete a case and its investigations; its evidence stays in the Locker (U1). */
  deleteCase: (caseId: string) =>
    request<DeletionReport>(`${BASE}/cases/${caseId}`, { method: "DELETE" }),

  /** Delete one finished investigation everywhere it is held (U1). */
  /** Every finished investigation (U10, Settings); running ones are skipped. */
  deleteAllMissions: () => request<DeletionReport>(`${BASE}/missions?confirm=delete`, { method: "DELETE" }),

  deleteMission: (runId: string) =>
    request<DeletionReport>(`${BASE}/missions/${runId}`, { method: "DELETE" }),

  openCase: (body: { title: string; description?: string; severity?: CaseSeverity; mode?: "GENERAL" | "CYBER" }) =>
    request<Case>(`${BASE}/cases`, { method: "POST", body: JSON.stringify(body) }),

  getCase: (caseId: string) => request<CaseDetail>(`${BASE}/cases/${caseId}`),

  updateCase: (
    caseId: string,
    body: {
      title?: string;
      description?: string;
      severity?: CaseSeverity;
      status?: CaseStatus;
      owner?: string;
      mode?: "GENERAL" | "CYBER";
      recall_similar?: boolean;
      pinned?: boolean;
    },
  ) => request<Case>(`${BASE}/cases/${caseId}`, { method: "PATCH", body: JSON.stringify(body) }),

  /** Indicators, relations, decoded commands and timelines from the run's security logs (Phase 52). */
  getCyber: (runId: string) => request<CyberAnalysis>(`${BASE}/missions/${runId}/cyber`),

  /** One quality figure with its formula, categories and trend (Phase 54). */
  /** The newest benchmark (B1); BENCHMARK_NOT_RUN until one is run locally. */
  getBenchmark: () => request<BenchmarkReport>(`${BASE}/evaluation/benchmark`),

  getQuality: () => request<QualitySummary>(`${BASE}/evaluation/quality`),

  /** The attack path as the 3D explorer draws it (Phase 53). */
  getAttackGraph: (runId: string) =>
    request<KnowledgeGraphView>(`${BASE}/missions/${runId}/attack-graph`),

  // --- the Evidence Locker (Phase 43) ---
  listEvidence: () => request<EvidenceList>(`${BASE}/evidence`),

  getEvidence: (evidenceId: string) => request<EvidenceDetail>(`${BASE}/evidence/${evidenceId}`),

  verifyEvidence: (evidenceId: string) =>
    request<IntegrityCheck>(`${BASE}/evidence/${evidenceId}/verify`, { method: "POST" }),

  updateEvidence: (
    evidenceId: string,
    body: { classification?: string; source?: string; authority?: string; authority_reason?: string; case_id?: string },
  ) =>
    request<EvidenceItem>(`${BASE}/evidence/${evidenceId}`, { method: "PATCH", body: JSON.stringify(body) }),

  evidenceDownloadUrl: (evidenceId: string) => `${BASE}/evidence/${evidenceId}/download`,

  /** Source authority tiers, highest first (Phase 45). */
  authorityTiers: () => request<AuthorityTier[]>(`${BASE}/evidence/authority`),

  // --- stored retrieval (Phase 40) ---
  listWorkspaces: () => request<string[]>(`${BASE}/context/workspaces`),

  getWorkspace: (workspaceId: string) =>
    request<WorkspaceView>(`${BASE}/context/workspaces/${encodeURIComponent(workspaceId)}`),

  retrieveContext: (body: { workspace_id: string; query: string; k?: number; min_score?: number; documents?: string[] }) =>
    request<RetrieveResponse>(`${BASE}/context/retrieve`, { method: "POST", body: JSON.stringify(body) }),

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

  forgetRun: (runId: string) =>
    request<{ run_id: string; episodes: number; episodic: boolean; semantic: boolean }>(
      `${BASE}/memory/runs/${runId}`,
      { method: "DELETE" },
    ),

  getEntityMemory: (name: string) =>
    request<EntityMemory>(`${BASE}/memory/entities/${encodeURIComponent(name)}`),
};
