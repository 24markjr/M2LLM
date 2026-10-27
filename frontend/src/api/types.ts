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
  /** The case the investigation belongs to (Phase 44); "" or absent outside any case. */
  case_id?: string;
  /** How it was asked to run (Phase U4): each mode makes operations required in the plan. */
  mode?: "investigate" | "compare" | "timeline" | "security";
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
  /** Documents flagged by the prompt-injection scan (Phase 27). Each was still read, as data.
   *  Optional: recordings made before Phase 27 do not carry it. */
  security_flags?: InjectionScan[];
  /** The mission's knowledge base (Phase 31): "neo4j", "memory", or "" when none was built.
   *  Optional: recordings made before Phase 31 do not carry these. */
  knowledge_store?: string;
  knowledge_entities?: number;
  knowledge_claims?: number;
  knowledge_conflicts?: number;
  /** The Evidence Locker (Phase 43): document name -> the evidence item the mission read. Optional:
   *  recordings made before Phase 43 do not carry it. */
  evidence?: Record<string, string>;
  /** Documents left out because they failed their integrity check, with the reason. */
  excluded_documents?: Record<string, string>;
  /** Each document's source authority tier (Phase 45). */
  authority?: Record<string, string>;
}

export type InjectionSeverity = "NONE" | "MEDIUM" | "HIGH";

export interface InjectionScan {
  source: string;
  /** category -> the phrases that matched */
  hits: Record<string, string[]>;
  severity: InjectionSeverity;
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
  /** The step in plain language, in the tense of its status (Phase 44). Absent in older recordings. */
  label?: string;
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
  /** Phase 46: the named factors, the weighted sum before the resolution gate, and penalties. */
  factors?: ConfidenceFactor[];
  weighted?: number;
  penalty?: number;
}

export interface ConfidenceFactor {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  reason: string;
  assessed: boolean;
}

/** Where each part's records are kept right now (Phase U1). */
export interface StoreStatus {
  part: string;
  store: string;
  note: string;
}

/** The benchmark (Phase B1): every system scored against the answer key by one deterministic judge. */
export interface BenchmarkSystem {
  system: string;
  scenarios: number;
  correct: number | null;
  factscore: number | null;
  invented: number;
  citation_precision: number | null;
  citations: number;
  false_alarms: number;
  alarm_cases: number;
  mean_latency_s: number;
  errors: number;
}

export interface BenchmarkScore {
  scenario_id: string;
  system: string;
  claims: number;
  correct: number | null;
  supported: number;
  sentences: number;
  invented: string[];
  citations: number;
  citations_precise: number;
  false_alarm: boolean | null;
  latency_ms: number;
  error: string;
  answer: string;
}

export interface BenchmarkReport {
  generated_at: string;
  model: string;
  prompt_version: number;
  method: string;
  systems: BenchmarkSystem[];
  results: BenchmarkScore[];
  skipped: Record<string, string>;
}

/** Evaluation v2 (Phase 54): one quality figure, its components, categories and trend. */
export interface QualitySummary {
  formula: string;
  value: number | null;
  components: { name: string; value: number; formula: string; source: string; dataset: string }[];
  categories: {
    category: string;
    scenarios: string[];
    metrics: Record<string, number> & { unsupported_claim_rate: number; verification_success: number };
    negative_passed: number | null;
    claims_found: number | null;
  }[];
  /** Phase B2: the multimodal suite by kind of file, from its newest report (absent before B2). */
  file_types?: QualitySummary["categories"];
  file_types_source?: string;
  agent_formula: string;
  trend: { generated_at: string; report: string; agent_quality: number; comparable_key: string }[];
  missing: string[];
}

/** What a run's security logs show (Phase 52). */
export interface CyberRelation {
  subject: string;
  predicate: string;
  object: string;
  sources: string[];
  first_seen: string;
  last_seen: string;
  detail: string;
}

export interface CyberAnalysis {
  events: number;
  documents: string[];
  indicators: { kind: string; value: string; defanged: boolean; sources: string[]; via: string[] }[];
  entities: { kind: string; name: string; sources: string[] }[];
  relations: CyberRelation[];
  host_timelines: Record<string, { time: string; locator: string; summary: string }[]>;
  account_timelines: Record<string, { time: string; locator: string; summary: string }[]>;
  decoded_commands: { locator: string; host: string; user: string; script: string }[];
  similar_cases: { case_id: string; run_id: string; shared: string[] }[];
  recall: string;
  /** Phase 53: ATT&CK techniques mapped by rule, and the attack path. */
  techniques?: TechniqueMapping[];
  attack_path?: { observed: PathEdge[]; inferred: PathEdge[] };
  attack_version?: string;
}

export interface TechniqueMapping {
  technique_id: string;
  name: string;
  tactics: string[];
  url: string;
  rule: string;
  source: string;
  indicators: string[];
  evidence: string[];
  hosts: string[];
  first_seen: string;
  needs_validation: boolean;
}

export interface PathEdge {
  kind: "OBSERVED" | "INFERRED";
  subject: string;
  predicate: string;
  object: string;
  sources: string[];
  reason: string;
  techniques: string[];
  time: string;
}

/** The investigation report (Phase 51). */
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

export interface ReportFinding {
  finding_id: string;
  claim: string;
  statement: string;
  severity: Severity;
  severity_reason: string;
  confidence: number;
  confidence_explained: string;
  verification: string;
  review: string;
  challenge: string;
  citations: string[];
  unit_issues: string[];
}

export interface InvestigationReport {
  report_id: string;
  run_id: string;
  case_id: string;
  objective: string;
  generated_at: string;
  model: string;
  content_hash: string;
  risk: Severity;
  risk_reason: string;
  executive_summary: string[];
  established: ReportFinding[];
  awaiting_review: ReportFinding[];
  not_established: ReportFinding[];
  recommendations: string[];
  limitations: string[];
  unknowns: string[];
  contradictions: string[];
  hypotheses: string[];
}

/** Human review of findings and the audit log (Phase 50). */
export type ReviewState = "PENDING" | "APPROVED" | "REJECTED" | "MODIFIED";

export interface ReviewDecision {
  decision_id: number;
  run_id: string;
  finding_id: string;
  state: ReviewState;
  reviewer: string;
  reason: string;
  modified_claim: string;
  at: string;
}

export interface FindingReview {
  run_id: string;
  finding_id: string;
  claim: string;
  statement_type: string;
  required: boolean;
  required_because: string[];
  state: ReviewState;
  history: ReviewDecision[];
}

export interface ReviewList {
  run_id: string;
  store: string;
  reviews: FindingReview[];
}

export interface ReviewResponse {
  review: FindingReview;
  follow_up_run_id: string;
  facts_remembered: number;
}

export interface AuditEntry {
  entry_id: number;
  at: string;
  actor: string;
  action: string;
  target: string;
  status_code: number | null;
  details: Record<string, unknown>;
}

/** The plan as a person reads it (Phase 49). */
export interface PlanStep {
  task_id: string;
  label: string;
  task_type: string;
  why: string;
  inputs: string[];
  action: string;
  output: string;
  depends_on: string[];
  status: TaskStatus;
  inserted_by_revision: number;
}

export interface PlanWorkstream {
  name: string;
  steps: PlanStep[];
}

export interface PlanChange {
  revision: number;
  trigger: string;
  reason: string;
  triggered_by: string;
  added: PlanStep[];
  skipped: string[];
  tasks_before: number;
  tasks_after: number;
}

export interface PlanTree {
  run_id: string;
  objective: string;
  workstreams: PlanWorkstream[];
  changes: PlanChange[];
  repairs: string[];
}

/** A counter-analysis of one finding (Phase 48). */
export interface CounterEvidence {
  locator: string;
  text: string;
  reason: string;
  authority: string;
  stronger: boolean;
}

export interface ChallengeResult {
  finding_id: string;
  claim: string;
  outcome: "WITHSTOOD" | "CONTESTED" | "OVERTURNED";
  summary: string;
  counter_evidence: CounterEvidence[];
  own_lines: string;
  negation_check: string;
  authority_note: string;
  confidence_before: number;
  confidence_after: number;
  after: Confidence;
  challenged_by: string;
  challenged_at: string;
}

/** Competing explanations, tested against the findings (Phase 47). */
export type HypothesisStatus = "SUPPORTED" | "OPEN" | "REJECTED";

export interface FindingRelation {
  finding_id: string;
  relation: "SUPPORTS" | "CONTRADICTS" | "NEUTRAL";
  confidence: number;
}

export interface Lead {
  locator: string;
  text: string;
}

export interface NextEvidence {
  kind: "SEARCH" | "ANALYST_REQUEST";
  text: string;
  query: string;
  leads: Lead[];
}

export interface Hypothesis {
  hypothesis_id: string;
  statement: string;
  supporting: FindingRelation[];
  contradicting: FindingRelation[];
  support: number;
  against: number;
  status: HypothesisStatus;
  status_reason: string;
  decisive_evidence: string;
  next_evidence: NextEvidence | null;
}

export interface HypothesisSet {
  question: string;
  hypotheses: Hypothesis[];
  determined: boolean;
  summary: string;
  skipped_reason: string;
  llm_calls: number;
}

/** A finding's evidence chain (Phase 46): claim to conclusion. */
export interface ChainEvidence {
  locator: string;
  document: string;
  resolved: boolean;
  note: string;
  evidence_id: string;
  authority: string;
  text: string;
  extractions: string[];
}

export interface ChainStep {
  kind: "CLAIM" | "EVIDENCE" | "EXTRACTION" | "REASONING" | "VERIFICATION" | "CONCLUSION";
  title: string;
  detail: string;
}

export interface FindingChain {
  run_id: string;
  finding: Finding;
  why: string[];
  evidence: ChainEvidence[];
  steps: ChainStep[];
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
  /** What kind of statement it is (Phase 45), computed from its evidence. */
  statement_type?: StatementType;
  /** The evidence basis under it; differs for a CONTRADICTION or a proposed RISK. */
  statement_basis?: StatementType;
  /** The model's word for it, kept to show the ruling decided. */
  proposed_type?: string;
}

export type StatementType =
  | "FACT"
  | "SOURCE_CLAIM"
  | "INFERENCE"
  | "HYPOTHESIS"
  | "CONTRADICTION"
  | "RISK"
  | "RECOMMENDATION"
  | "OBSERVATION"
  | "UNKNOWN";

/** A source authority tier (Phase 45), from `.agent/config/authority.yaml`. */
export interface AuthorityTier {
  id: string;
  label: string;
  description: string;
  weight: number;
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

/** One sentence of the model-written narrative, judged against the report's evidence (Phase 37). */
export interface SentenceCheck {
  sentence: string;
  status: string;
  reasoning: string;
  /** Dates and figures no cited line contains, and numbers standing where a date belongs. */
  ungrounded: string[];
}

/** The verification receipt (Phase U7): counted from the run, hashed over itself. */
export interface ReceiptDocument {
  name: string;
  sha256: string;
  characters: number;
  evidence_id: string;
}

export interface ReceiptFinding {
  finding_id: string;
  claim: string;
  classification: string;
  verification: string;
  verifier: string;
  degraded: boolean;
  confidence: number;
  citations: number;
  citations_resolved: number;
}

export interface AnswerTally {
  sentences: number;
  supported: number;
  partial: number;
  unsupported: number;
  contradicted: number;
  insufficient: number;
}

export interface Receipt {
  run_id: string;
  question: string;
  model: string;
  prompt_versions: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
  documents: ReceiptDocument[];
  findings: ReceiptFinding[];
  answer: AnswerTally;
  tasks_planned: number;
  tasks_completed: number;
  gaps_open: number;
  receipt_hash: string;
}

/** One answer in the plain-model comparison (Phase U7), scored by the same sentence checker. */
export interface AnswerSide {
  label: string;
  answer: string;
  check: NarrativeCheck | null;
  tally: AnswerTally;
  ungrounded: string[];
  cited_findings: number;
  latency_ms: number;
}

export interface Comparison {
  run_id: string;
  question: string;
  model: string;
  evidence_lines: number;
  truncated: boolean;
  baseline_prompt_version: number;
  plain: AnswerSide;
  jarvis: AnswerSide;
  generated_at: string;
}

export interface NarrativeCheck {
  section: string;
  overall: string;
  sentences: SentenceCheck[];
}

export interface Limitation {
  description: string;
  cause: string;
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
  /** What constrains trust in the report, with its cause (BUG-041: was typed as strings). */
  limitations: Limitation[];
  execution: ExecutionSummary;
  /** Absent on reports recorded before Phase 37. */
  narrative_checks?: NarrativeCheck[];
}

/** The body of every failed request. The UI renders codes, never message text. */
export interface ApiErrorBody {
  error_code: string;
  message: string;
  run_id: string | null;
  details: Record<string, unknown>;
}

// --- recordings and evaluation reports ----------------------------------------

export interface RecordingSummary {
  run_id: string;
  file: string;
  objective: string;
  model: string;
  outcome: string;
  recorded_at: string;
  event_count: number;
  duration_ms: number;
  /** Committed to the repo rather than local scratch. */
  committed: boolean;
  /** Phase U1: what it found, its case, and why it is hidden from the default list ("" = shown). */
  findings?: number;
  verified?: number;
  case_id?: string;
  hidden?: string;
}

/**
 * A recorded run. `events` give the timing, `snapshot` gives the content.
 *
 * That split is what makes a replay faithful: event payloads are summaries (a truncated claim,
 * a rounded confidence), so a replay driven by events alone could animate the graph but never
 * drill into a finding's evidence. The snapshot holds the same payloads the live routes serve.
 */
export interface Recording {
  run_id: string;
  objective: string;
  recorded_at: string;
  model: string;
  outcome: string;
  events: EventRecord[];
  snapshot: {
    mission?: MissionDetail;
    tasks?: TaskGraphResponse;
    findings?: { run_id: string; findings: Finding[] };
    gaps?: GapRecord[];
    report?: FinalReport;
    /** The plan tree and its changes (Phase 49); absent in recordings made before it. */
    plan?: PlanTree;
    /** Competing explanations (Phase 47); absent in recordings made before it. */
    hypotheses?: HypothesisSet;
    /** The run's knowledge graph, so replay opens the 3D explorer from the recording (absent before this fix). */
    knowledge?: { snapshot: KnowledgeSnapshot; timeline: TimelineEvent[]; graph: KnowledgeGraphView };
    /** The text each file was read as (U6); absent in recordings made before it. */
    sources?: Record<string, string>;
    /** The receipt and the plain-model comparison (U7); absent in recordings made before it. */
    receipt?: Receipt;
    comparison?: Comparison;
  };
}

export interface MetricPoint {
  generated_at: string;
  model: string;
  config_hash: string;
  prompt_versions: Record<string, number>;
  suite: string;
  metrics: Record<string, number>;
  confabulations: number;
  blind_spots: number;
  /**
   * Points may only be joined into a line within one key. Two reports from different models or
   * prompt versions describe different systems, and a line between them shows a change that
   * never happened.
   */
  comparable_key: string;
}

/** Whether higher or lower is better. Served by the API so the UI cannot hold a stale copy. */
export type MetricDirections = Record<string, "higher" | "lower">;

// --- The knowledge layer (Phases 28-31) ----------------------------------------------------

export type EntityType = "PERSON" | "ORG" | "LOCATION" | "DATE" | "PRODUCT" | "SHIPMENT" | "OTHER";
export type GraphNodeKind = "ENTITY" | "CLAIM" | "DOCUMENT" | "FINDING";
export type GraphLinkKind =
  | "RELATES"
  | "HAS_CLAIM"
  | "CITED_IN"
  | "MENTIONED_IN"
  | "CONFLICTS_WITH"
  | "CITES"
  /** The same attribute described in other words: not a contradiction (BUG-033). */
  | "DIFFERS_FROM"
  | "INFERRED"
  | "MAPS_TO";

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  entity_type: EntityType | null;
  /** The entity a claim belongs to: claims are sub-nodes of their entity. */
  parent: string | null;
  claim_count: number;
  conflict_count: number;
  grounded: boolean;
  source: string;
  status: string;
}

export interface GraphLink {
  source: string;
  target: string;
  kind: GraphLinkKind;
  label: string;
}

export interface KnowledgeGraphView {
  run_id: string;
  store: string;
  focus: string | null;
  depth: number;
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface KnowledgeEntity {
  entity_id: string;
  name: string;
  entity_type: EntityType;
  aliases: string[];
  sources: string[];
}

export interface KnowledgeClaim {
  claim_id: string;
  entity_id: string;
  attribute: string;
  value: string;
  source: string;
  document_id: string;
  line: number | null;
  quote: string;
  grounded: boolean;
}

export interface ConflictSide {
  value: string;
  claim_ids: string[];
  sources: string[];
}

export interface ClaimConflict {
  conflict_id: string;
  entity_id: string;
  entity_name: string;
  attribute: string;
  kind: "DATE" | "NUMBER" | "TEXT";
  sides: ConflictSide[];
  /** Every side from one document: check the context (a planned and an actual date, say). */
  same_document?: boolean;
}

export interface KnowledgeRelationship {
  relationship_id: string;
  subject_id: string;
  predicate: string;
  object_id: string;
  source: string;
}

export interface NodeDetail {
  node: GraphNode;
  entity: KnowledgeEntity | null;
  claims: KnowledgeClaim[];
  conflicts: ClaimConflict[];
  differences?: ClaimConflict[];
  relationships: KnowledgeRelationship[];
  documents: string[];
  entities: KnowledgeEntity[];
  finding_claim: string;
  finding_status: string;
}

export interface FindingTrail {
  finding_id: string;
  claim: string;
  status: string;
  node_ids: string[];
  links: GraphLink[];
  unmatched_sources: string[];
}

export interface KnowledgeSummary {
  run_id: string;
  store: string;
  entities: number;
  relationships: number;
  claims: number;
  conflicts: number;
  /** Differing descriptions (BUG-033): not contradictions. */
  differences?: number;
  stats?: ExtractionStats;
  knowledge_pass_task_id: string | null;
}

/** What building the knowledge base read and could not do. */
export interface ExtractionStats {
  documents: number;
  chunks: number;
  chunks_skipped: number;
  llm_calls: number;
  failed_chunks: number;
  claims: number;
  ungrounded_claims: number;
  /** Documents at least one part of which was read (BUG-034). */
  documents_read?: number;
  contact_claims_skipped?: number;
}

export interface AnalyzeResponse {
  snapshot: KnowledgeSnapshot;
  timeline: TimelineEvent[];
  graph: KnowledgeGraphView;
  excluded: string[];
}

// --- Member 3's investigation views (Phase 36) ---------------------------------------------

/** A knowledge base, whole: what `analyze` returns, so its views can be built in the browser. */
export interface KnowledgeSnapshot {
  entities: KnowledgeEntity[];
  relationships: KnowledgeRelationship[];
  claims: KnowledgeClaim[];
  conflicts: ClaimConflict[];
  /** Differing descriptions (BUG-033). Absent in knowledge built before 2026-10-07. */
  differences?: ClaimConflict[];
}

/** A date as far as the text gives it: a year may be missing, and a day. */
export interface PartialDate {
  year: number | null;
  month: number;
  day: number | null;
}

export type TimelineRelation = "SAME_TIME_AS" | "AFTER" | "UNKNOWN";

export interface TimelineEvent {
  claim_id: string;
  entity_id: string;
  entity_name: string;
  attribute: string;
  value: string;
  source: string;
  date: PartialDate | null;
  /** The year used for ordering was inferred from the other events, not read from this one. */
  year_inferred: boolean;
  relation_to_previous: TimelineRelation | null;
}

export type ClaimOrder = "A_BEFORE_B" | "A_AFTER_B" | "SAME_TIME" | "UNKNOWN";

export interface ClaimComparison {
  claim_a: KnowledgeClaim;
  claim_b: KnowledgeClaim;
  date_a: PartialDate | null;
  date_b: PartialDate | null;
  relation: ClaimOrder;
  reason: string;
}

/** A claim ranked by Member 3's explainable score: every point has a reason. */
export interface SearchHit {
  claim: KnowledgeClaim;
  entity_name: string;
  score: number;
  explanation: string[];
}

export interface NetworkNode {
  entity_id: string;
  name: string;
  entity_type: EntityType;
}

export interface NetworkEdge {
  from_id: string;
  to_id: string;
  predicate: string;
  source: string;
}

export interface EntityNetwork {
  center_id: string;
  depth: number;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}

/** Member 3's `/investigation/{name}`: everything known about one entity. */
export interface EntityInvestigation {
  entity: KnowledgeEntity;
  sources: string[];
  network: EntityNetwork;
  claims: KnowledgeClaim[];
  conflicts: ClaimConflict[];
}

// --- documents of every kind (Phase 38) -----------------------------------------------------

/** One family of file types the engine reads: from `GET /documents/formats`. */
export interface FormatSpec {
  kind: string;
  extensions: string[];
  parser: string;
  /** False for images and video until OCR and transcription: accepted, but no text yet. */
  yields_text: boolean;
  becomes: string;
}

/** What an upload parsed as. The parse result, not an acknowledgement. */
export interface UploadedDocument {
  document_id: string;
  name: string;
  kind: string;
  bytes: number;
  summary: string;
  truncated: boolean;
  injection: { source: string; hits: Record<string, string[]>; severity: string };
  parser: string;
  sha256: string;
  has_text: boolean;
  /** Why a file has no text yet, when it has none. */
  note: string;
  /** For images, scans, video, audio (Phase 39): lines read, segments heard, lines seen and by which model. */
  understood: string;
  /** Stored retrieval (Phase 40): where the file was ingested. Null without text, or when the store failed. */
  ingested?: Ingested | null;
  /** Being embedded for search after the response (2026-10-06); listed by the workspace until done. */
  indexing?: boolean;
  /** The Evidence Locker item this upload is (Phase 43), and the locker holding its custody. */
  evidence_id?: string;
  custody?: string;
}

// --- stored, workspace-scoped retrieval (Phase 40) ---

export interface Ingested {
  workspace_id: string;
  document_id: string;
  chunks: number;
  /** Same SHA-256 as last time: nothing was re-embedded. */
  unchanged: boolean;
  store: string;
}

export interface WorkspaceDocument {
  workspace_id: string;
  document_id: string;
  kind: string;
  sha256: string;
  parser: string;
  /** `lines` or `chars`: which chunker cut it (Phase 41). */
  chunker: string;
  chunks: number;
}

export interface WorkspaceView {
  workspace_id: string;
  documents: WorkspaceDocument[];
  /** `pgvector`, or `memory` when the database is down. */
  store: string;
  /** Uploads still being indexed in the background, by name (any workspace). */
  indexing: string[];
}

export interface RetrievalHit {
  /** A citation, e.g. `report.txt:r12`. */
  source: string;
  document_id: string;
  line: number | null;
  text: string;
  score: number;
}

export interface RetrieveResponse {
  store: string;
  workspace_id: string;
  hits: RetrievalHit[];
}

/** An earlier upload, offered again to a new mission. */
export interface StoredDocument {
  name: string;
  kind: string;
  bytes: number;
  uploaded_at: string;
  evidence_id?: string;
}

// --- memory across investigations (Phase 33) ------------------------------------------------

export interface MemoryStatus {
  episodic: boolean;
  /** "neo4j" or "postgres"; empty when the store holding facts is unreachable. */
  semantic_store: string;
}

export interface Episode {
  episode_id: string;
  run_id: string;
  objective: string;
  claim: string;
  sources: string[];
  verification_status: string;
  created_at: string;
}

export interface WorkingMemorySnapshot {
  investigation_id: string;
  objective: string;
  plan_steps: string[];
  evidence_count: number;
  hypotheses: string[];
  findings: string[];
  started_at: string | null;
}

export interface InvestigationMemory {
  investigation: { run_id: string; objective: string; snapshot: WorkingMemorySnapshot; archived_at: string };
  episodes: Episode[];
}

export type FactKind = "ATTRIBUTE" | "RELATION";

/** No confidence: support says which runs asserted the fact, and from which lines. */
export interface Fact {
  fact_id: string;
  kind: FactKind;
  subject: string;
  predicate: string;
  object: string;
  support: { run_id: string; source: string }[];
  support_count: number;
  runs: string[];
}

export interface KnownEntity {
  key: string;
  name: string;
  entity_types: EntityType[];
  aliases: string[];
  runs: string[];
}

export interface EntityMemory {
  entity: KnownEntity;
  facts: Fact[];
}

// --- the Evidence Locker (Phase 43) ---

export type IntegrityStatus = "VERIFIED" | "FAILED" | "UNCHECKED";

export interface EvidenceItem {
  evidence_id: string;
  sha256: string;
  name: string;
  kind: string;
  parser: string;
  bytes: number;
  collected_at: string;
  collected_by: string;
  source: string;
  classification: "UNCLASSIFIED" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED";
  /** Source authority tier (Phase 45) and why it is that tier. */
  authority?: string;
  authority_reason?: string;
  integrity: IntegrityStatus;
  integrity_checked_at: string | null;
  case_id: string | null;
}

export interface CustodyEvent {
  event_id: number;
  evidence_id: string;
  action: string;
  actor: string;
  at: string;
  details: Record<string, unknown>;
}

export interface EvidenceCitation {
  run_id: string;
  finding_id: string;
  locator: string;
  claim: string;
  at: string;
}

export interface EvidenceList {
  /** `postgres`, or `memory` when the database is down: custody then is not durable. */
  locker: string;
  items: { item: EvidenceItem; citations: number }[];
  imported: number;
}

export interface EvidenceDetail {
  locker: string;
  item: EvidenceItem;
  custody: CustodyEvent[];
  citations: EvidenceCitation[];
  versions: EvidenceItem[];
}

export interface IntegrityCheck {
  evidence_id: string;
  integrity: IntegrityStatus;
  expected: string;
  stored: string | null;
  working: string | null;
  reason: string;
}

// --- cases (Phase 44) ---

export type CaseSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type CaseStatus = "OPEN" | "INVESTIGATING" | "REVIEW" | "CLOSED";

export interface Case {
  case_id: string;
  title: string;
  description: string;
  severity: CaseSeverity;
  status: CaseStatus;
  owner: string;
  mode: "GENERAL" | "CYBER";
  /** Opt-in recall of similar cases, as context (Phase 52). */
  recall_similar?: boolean;
  /** Kept at the top of the sidebar (Phase U1). */
  pinned?: boolean;
  opened_at: string;
  closed_at: string | null;
}

/** What a deletion removed, and what is kept by design (Phase U1). */
export interface DeletionReport {
  deleted: string[];
  removed: string[];
  kept: string[];
  skipped: string[];
}

export interface CaseCounters {
  investigations: number;
  running: number;
  evidence: number;
  failed_integrity: number;
  findings: number;
  verified: number;
  contradictions: number;
  open_gaps: number;
}

export interface CaseInvestigation {
  case_id: string;
  run_id: string;
  objective: string;
  status: string;
  findings: number;
  verified: number;
  contradictions: number;
  open_gaps: number;
  created_at: string;
  finished_at: string | null;
}

export interface CaseList {
  /** `postgres`, or `memory` when the database is down: cases then are not durable. */
  store: string;
  cases: { case: Case; counters: CaseCounters }[];
}

export interface CaseDetail {
  store: string;
  case: Case;
  counters: CaseCounters;
  investigations: CaseInvestigation[];
  evidence: { item: EvidenceItem; added_at: string; added_by: string }[];
}

// --- the investigation conversation (v4 Phase 3) ---------------------------------------------

export type StopReason = "ANSWERED" | "ASKED_USER" | "STEP_LIMIT" | "FAILED" | "RECHECKED";

export interface AnsweredClaim {
  text: string;
  citations: string[];
  // The verifier's verdict, or UNVERIFIED when nothing it cites is a line of the case.
  status: string;
  issues: string[];
}

export interface ToolStep {
  tool: string;
  arguments: Record<string, unknown>;
  result: string;
}

export interface Recheck {
  run_id: string;
  finding_id: string;
  claim: string;
  before: string;
  after: string;
  changed: boolean;
  reason: string;
}

export interface Turn {
  turn_id: string;
  role: "user" | "assistant";
  text: string;
  actor: string;
  claims: AnsweredClaim[];
  steps: ToolStep[];
  stop_reason: StopReason | null;
  findings_referred: string[];
  rechecks: Recheck[];
  question: string;
  pinned: boolean;
  // v4 Phase 4: replaced by a regenerated answer or an edited message, kept and shown on request.
  superseded: boolean;
  replaces: string;
  created_at: string;
}

export interface Thread {
  case_id: string;
  turns: Turn[];
}

// --- following an investigation up (v4 Phase 3b) ---------------------------------------------

export interface HistoryEntry {
  at: string | null;
  kind: string;
  summary: string;
  by: string;
}

export interface FindingHistory {
  run_id: string;
  finding_id: string;
  claim: string;
  entries: HistoryEntry[];
}

export interface RunPair {
  a: string;
  b: string;
  claim_a: string;
  claim_b: string;
  status_a: string;
  status_b: string;
  change: "same" | "status changed" | "only in a" | "only in b";
}

export interface RunComparison {
  case_id: string;
  a: string;
  b: string;
  pairs: RunPair[];
}

export interface StaleFinding {
  run_id: string;
  finding_id: string;
  claim: string;
  finished_at: string;
  newer_evidence: string[];
}

/** One export of an investigation report (v4 Phase 5), signed with its hashes. */
export interface ReportVersion {
  version: number;
  format: string;
  report_id: string;
  content_hash: string;
  receipt_hash: string;
  snapshot_hash: string;
  findings: Record<string, string>;
  evidence: string[];
  actor: string;
  exported_at: string;
}

// --- operating the organisation (v4 Phase 8) --------------------------------------------------

export interface RunMetrics {
  run_id: string;
  status: string;
  created_at: string;
  queue_wait_s: number;
  duration_s: number;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  model_seconds: number;
  cost_inr: number;
  error: string;
}

export interface OpsSummary {
  days: number;
  investigations: number;
  completed: number;
  failed: number;
  cancelled: number;
  running: number;
  waiting: number;
  error_rate: number;
  duration_p50_s: number;
  duration_p95_s: number;
  queue_wait_p50_s: number;
  llm_calls: number;
  tokens: number;
  cost_total_inr: number;
  cost_per_investigation_inr: number;
  rates: Record<string, number>;
  by_day: { day: string; investigations: number; failed: number; cost_inr: number }[];
  recent_errors: RunMetrics[];
  model: string;
  model_healthy: boolean;
}

export interface GovernancePolicy {
  retention_days: number;
  mask_personal_data: boolean;
  pack: string;
}

export interface RetentionResult {
  retention_days: number;
  dry_run: boolean;
  deleted: string[];
  kept_running: string[];
}

export interface SubjectReport {
  identifier: string;
  hits: { where: string; run_id: string; case_id: string; location: string; excerpt: string }[];
  investigations: string[];
  conversations: string[];
  evidence_files: string[];
  erased: boolean;
}

// --- breadth (v4 Phase 10) -----------------------------------------------------------------------

export interface DomainPack {
  id: string;
  name: string;
  description: string;
  starter_questions: string[];
}

export interface Packs {
  current: string;
  packs: DomainPack[];
}

export interface WatchView {
  enabled: boolean;
  rerun_on_new_files: boolean;
  rerun_every_days: number;
  last_rerun_at: string | null;
  seen: Record<string, string>;
  folder: string;
}

export interface WatchScan {
  case_id: string;
  folder: string;
  taken: string[];
  rerun: string;
  reason: string;
}
