/**
 * The investigation journal's logic (Phase U5): what the engine is doing, in plain words; the answer
 * sentence by sentence with its status; citations; and the three closing sections. Pure, so it is
 * tested without a browser, and shared by a live run and a replay.
 */

import type {
  EventRecord,
  Finding,
  FinalReport,
  GapRecord,
  HypothesisSet,
  TaskGraphResponse,
} from "../api/types";
import { statusOf, type Status } from "../ui/status";

// --- steps ---------------------------------------------------------------------------------------

export type StepState = "done" | "doing" | "todo" | "skipped";

export interface Step {
  id: string;
  label: string;
  state: StepState;
  detail: string;
}

function count(events: EventRecord[], type: string): number {
  return events.filter((e) => e.event_type === type).length;
}

function last(events: EventRecord[], type: string): EventRecord | undefined {
  for (let i = events.length - 1; i >= 0; i--) if (events[i]?.event_type === type) return events[i];
  return undefined;
}

/**
 * Seven steps every investigation goes through, each with what happened in it so far. `finished`
 * marks every step that started as done, and the ones that never started as skipped.
 */
export function journalSteps(events: EventRecord[], tasks: TaskGraphResponse | null, finished: boolean): Step[] {
  const has = (type: string) => events.some((e) => e.event_type === type);
  const intent = last(events, "INTENT_CREATED");
  const plan = last(events, "PLAN_CREATED");
  const nodes = tasks?.nodes ?? [];
  const doneTasks = nodes.filter((n) => n.status === "COMPLETED").length;
  const findings = count(events, "FINDING_CREATED");
  const discarded = count(events, "FINDING_DISCARDED");
  const verified = events.filter((e) => e.event_type === "FINDING_VERIFIED" && e.payload.status === "SUPPORTED").length;
  const checked = count(events, "FINDING_VERIFIED") + count(events, "FINDING_REJECTED");
  const gaps = count(events, "EVIDENCE_GAP_DETECTED");
  const closed = count(events, "EVIDENCE_GAP_RESOLVED");
  const replans = count(events, "REPLAN_STARTED");
  const lastGap = last(events, "EVIDENCE_GAP_DETECTED");

  const raw: { id: string; label: string; started: boolean; complete: boolean; detail: string }[] = [
    {
      id: "understand",
      label: "Understanding the question",
      started: has("RUN_STARTED"),
      complete: !!intent,
      detail: intent ? `Goal: ${String(intent.payload.goal ?? "").replaceAll("_", " ")}` : "",
    },
    {
      id: "plan",
      label: "Planning the work",
      started: !!intent,
      complete: !!plan,
      detail: plan ? `${String(plan.payload.task_count ?? nodes.length)} step(s) planned` : "",
    },
    {
      id: "read",
      label: "Reading the files",
      started: has("TASK_STARTED"),
      complete: has("REASONING_STARTED") || has("FINDING_CREATED"),
      detail: nodes.length ? `${doneTasks} of ${nodes.length} step(s) done` : "",
    },
    {
      id: "reason",
      label: "Drawing findings from what was read",
      started: has("REASONING_STARTED") || findings > 0,
      complete: has("VERIFICATION_STARTED") || checked > 0,
      detail: findings || discarded
        ? `${findings} candidate finding(s)${discarded ? `, ${discarded} set aside` : ""}`
        : "",
    },
    {
      id: "verify",
      label: "Checking each finding against its lines",
      started: has("VERIFICATION_STARTED") || checked > 0,
      complete: has("VERIFICATION_COMPLETED") || has("SYNTHESIS_STARTED"),
      detail: checked ? `${verified} of ${checked} verified` : "",
    },
    {
      id: "gaps",
      label: "Looking for what is missing",
      started: gaps > 0 || replans > 0,
      complete: has("SYNTHESIS_STARTED"),
      detail: gaps
        ? `${gaps} gap(s), ${closed} closed${replans ? `, ${replans} new round(s) of work` : ""}${
            lastGap?.payload.missing ? ` - latest: ${String(lastGap.payload.missing)}` : ""
          }`
        : "",
    },
    {
      id: "write",
      label: "Writing the answer",
      started: has("SYNTHESIS_STARTED"),
      complete: has("SYNTHESIS_COMPLETED"),
      detail: "",
    },
  ];

  let doing = false;
  return raw.map((r) => {
    let state: StepState;
    if (r.complete) state = "done";
    else if (r.started && !finished && !doing) {
      state = "doing";
      doing = true;
    } else if (finished) state = r.started ? "done" : "skipped";
    else state = r.started ? "doing" : "todo";
    return { id: r.id, label: r.label, state, detail: r.detail };
  });
}

// --- the answer ----------------------------------------------------------------------------------

export interface AnswerSentence {
  text: string;
  status: Status;
  reasoning: string;
}

/**
 * The executive summary, sentence by sentence with the status the narrative check gave each (Phase
 * 37). A report without checks gives its summary as one unchecked passage.
 */
export function answerSentences(report: FinalReport | null): AnswerSentence[] {
  if (!report) return [];
  const summary = report.sections.find((s) => s.kind === "EXECUTIVE_SUMMARY");
  const check = report.narrative_checks?.find(
    (c) => c.section === "EXECUTIVE_SUMMARY" || c.section === summary?.heading,
  );
  if (check?.sentences.length) {
    return check.sentences.map((s) => ({ text: s.sentence, status: statusOf(s.status), reasoning: s.reasoning }));
  }
  const text = summary?.narrative.trim() ?? "";
  return text ? [{ text, status: "unknown", reasoning: "This summary was not checked sentence by sentence." }] : [];
}

// --- citations -----------------------------------------------------------------------------------

export interface Citation {
  key: string;
  label: string;
  document: string;
  href: string;
  resolved: boolean;
}

/** A finding's citations: the file and where in it, linked to its evidence item when it has one. */
export function citationsOf(finding: Finding, evidence: Record<string, string>): Citation[] {
  return finding.evidence.map((ref, i) => {
    const loc = ref.locator;
    const document = loc.document_name || loc.document_id;
    const where = loc.page !== null ? `p.${loc.page}` : loc.row !== null ? `line ${loc.row}` : "";
    const evidenceId = evidence[document] ?? evidence[loc.document_id];
    return {
      key: `${ref.evidence_id}-${i}`,
      label: where ? `${document} · ${where}` : document,
      document,
      href: evidenceId ? `#/evidence/${evidenceId}` : "",
      resolved: ref.resolution === "RESOLVED",
    };
  });
}

/** The status mark of a finding: its verification, or unknown before it is checked. */
export function findingStatus(finding: Finding): Status {
  return statusOf(finding.verification?.status);
}

// --- the closing sections ------------------------------------------------------------------------

export interface Closing {
  couldNot: string[];
  wouldChange: string[];
  next: string[];
}

/**
 * What every answer ends with: what could not be established, what would change the answer, and the
 * best next evidence to get. Each from the run's own record - gaps, rejected findings, limitations,
 * hypotheses - never written for the occasion.
 */
export function closingSections(
  findings: Finding[],
  gaps: GapRecord[],
  hypotheses: HypothesisSet | null | undefined,
  report: FinalReport | null,
): Closing {
  const couldNot: string[] = [];
  for (const gap of gaps) if (!gap.resolved) couldNot.push(gap.description);
  for (const f of findings) {
    if (findingStatus(f) === "unsupported") couldNot.push(`Not established: ${f.claim}`);
  }
  for (const limit of report?.limitations ?? []) {
    couldNot.push(limit.cause ? `${limit.description} (${limit.cause})` : limit.description);
  }

  const wouldChange: string[] = [];
  const next: string[] = [];
  for (const h of hypotheses?.hypotheses ?? []) {
    if (h.status === "OPEN" && h.decisive_evidence) wouldChange.push(`${h.statement} - ${h.decisive_evidence}`);
    if (h.status !== "REJECTED" && h.next_evidence?.text) next.push(h.next_evidence.text);
  }
  for (const f of findings) {
    if (findingStatus(f) === "inferred") wouldChange.push(`A line that states it outright, or contradicts it: ${f.claim}`);
  }
  return {
    couldNot: unique(couldNot),
    wouldChange: unique(wouldChange),
    next: unique(next),
  };
}

function unique(items: string[]): string[] {
  return [...new Set(items.map((s) => s.trim()).filter(Boolean))];
}
