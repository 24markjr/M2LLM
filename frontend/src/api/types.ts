/**
 * Wire types, mirroring `docs/openapi.json`.
 *
 * Hand-written rather than generated, and narrower than the schema on purpose: the UI reads
 * a subset of each response, and typing only what it reads means an unused field changing
 * shape does not break the build. `docs/openapi.json` remains the contract - regenerate it
 * with `python scripts/export_openapi.py` and reconcile here if a route's shape changes.
 */

export type MissionStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "CLARIFICATION_NEEDED"
  | "FAILED"
  | "CANCELLED";

export type Stage =
  | "UNDERSTANDING"
  | "PLANNING"
  | "EXECUTING"
  | "REASONING"
  | "VERIFYING"
  | "REPLANNING"
  | "SYNTHESIZING"
  | "DONE";

export type TaskStatus =
  | "PENDING"
  | "READY"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "SKIPPED"
  | "CANCELLED"
  | "BLOCKED";

/** How a citation resolved against what the tasks actually produced. */
export type Resolution = "RESOLVED" | "PARTIAL" | "UNRESOLVED";

export type VerificationStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "UNSUPPORTED"
  | "CONTRADICTED"
  | "INCONCLUSIVE";

export type Classification = "FACT" | "INFERENCE" | "HYPOTHESIS" | "UNKNOWN";

export interface MissionSummary {
  run_id: string;
  objective: string;
  status: MissionStatus;
  stage: Stage;
  documents: string[];
  created_at: string;
  finished_at: string | null;
  finding_count: number;
  verified_count: number;
  unresolved_gap_count: number;
}

export interface MissionDetail extends MissionSummary {
  goal: string;
  required_operations: string[];
  task_count: number;
  replan_iterations: number;
  termination_reason: string;
  error_code: string;
  error_message: string;
  clarification_question: string;
  has_report: boolean;
}

export interface TaskNode {
  task_id: string;
  task_type: string;
  description: string;
  status: TaskStatus;
  depends_on: string[];
  tool_id: string;
  /** The replanning loop inserted this task; the planner did not. */
  inserted_by_replan: boolean;
}

export interface TaskGraphResponse {
  run_id: string;
  nodes: TaskNode[];
  edges: [string, string][];
  /** Tasks that can run at the same time. Computed server side from the graph. */
  waves: string[][];
}

export interface EventRecord {
  event_id: string;
  event_type: string;
  /** Milliseconds since RUN_STARTED. Relative, so two traces are comparable. */
  t_offset_ms: number;
  task_id: string | null;
  finding_id: string | null;
  payload: Record<string, unknown>;
}

export interface EventPage {
  run_id: string;
  events: EventRecord[];
  total: number;
  offset: number;
  limit: number;
}

export interface SourceLocator {
  document_id: string;
  document_name: string;
  page: number | null;
  row: number | null;
  char_start: number | null;
  char_end: number | null;
}

export interface EvidenceRef {
  evidence_id: string;
  locator: SourceLocator;
  resolution: Resolution;
  resolution_note: string;
}

export interface Confidence {
  value: number;
  resolution_rate: number;
  evidence_strength: number;
  source_agreement: number;
  classification_ceiling: number;
}

export interface VerificationIssue {
  issue_type: string;
  description: string;
  severity: string;
}

export interface VerificationResult {
  status: VerificationStatus;
  issues: VerificationIssue[];
  /** The verifier fell back to the baseline checker; the check is weaker than it looks. */
  degraded: boolean;
  degraded_reason: string;
  verifier: string;
}

export interface Finding {
  finding_id: string;
  claim: string;
  classification: Classification;
  confidence: Confidence;
  evidence: EvidenceRef[];
  verification: VerificationResult | null;
  derived_from_task_ids: string[];
  revision: number;
}

export interface GapRecord {
  gap_id: string;
  gap_type: string;
  description: string;
  resolved: boolean;
  finding_id: string;
}

export interface ReportSection {
  heading: string;
  kind: string;
  narrative: string;
  items: string[];
  finding_ids: string[];
}

export interface ExecutionSummary {
  tasks_planned: number;
  tasks_completed: number;
  tasks_failed: number;
  tasks_skipped: number;
  tool_calls: number;
  documents_processed: number;
  replan_iterations: number;
  gaps_detected: number;
  gaps_resolved: number;
}

export interface FinalReport {
  run_id: string;
  objective: string;
  generated_at: string;
  overall_confidence: number;
  sections: ReportSection[];
  verified_findings: string[];
  uncertain_findings: string[];
  rejected_findings: string[];
  unresolved_gaps: string[];
  limitations: string[];
  execution: ExecutionSummary;
}

/** The body of every failed request. The UI renders codes, never message text. */
export interface ApiErrorBody {
  error_code: string;
  message: string;
  run_id: string | null;
  details: Record<string, unknown>;
}
