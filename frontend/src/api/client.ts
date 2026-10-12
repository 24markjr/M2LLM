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
  // A file upload sends FormData, whose content type (with its boundary) the browser must set.
  const isForm = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(init?.headers ?? {}) },
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

  /** `workspaceId` (Phase 40): the mission's documents are ingested there and searched by meaning. */
  createMission: (objective: string, documents: string[], workspaceId?: string, caseId?: string) =>
    request<MissionDetail>(`${BASE}/missions`, {
      method: "POST",
      body: JSON.stringify({
        objective,
        documents,
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
  listCases: () => request<CaseList>(`${BASE}/cases`),

  openCase: (body: { title: string; description?: string; severity?: CaseSeverity }) =>
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
    },
  ) => request<Case>(`${BASE}/cases/${caseId}`, { method: "PATCH", body: JSON.stringify(body) }),

  /** Indicators, relations, decoded commands and timelines from the run's security logs (Phase 52). */
  getCyber: (runId: string) => request<CyberAnalysis>(`${BASE}/missions/${runId}/cyber`),

  /** One quality figure with its formula, categories and trend (Phase 54). */
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
    body: { classification?: string; source?: string; authority?: string; authority_reason?: string },
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
