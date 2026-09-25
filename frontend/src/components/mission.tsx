/**
 * The operational components.
 *
 * One rule runs through all of them: **uncertainty is shown, not smoothed.** An unsupported
 * claim is not hidden and not quietly styled like a supported one; an unresolved citation says
 * so; a degraded verifier admits it. The system's honesty about what it does not know is the
 * thing worth demonstrating, and a UI that rounds it off throws that away.
 */

import { useState } from "react";

import type {
  EventRecord,
  FinalReport,
  Finding,
  GapRecord,
  Stage,
  TaskGraphResponse,
  TaskNode,
} from "../api/types";

const STAGES: Stage[] = [
  "UNDERSTANDING",
  "PLANNING",
  "EXECUTING",
  "REASONING",
  "VERIFYING",
  "REPLANNING",
  "SYNTHESIZING",
];

const STAGE_LABEL: Record<string, string> = {
  UNDERSTANDING: "Understanding",
  PLANNING: "Planning",
  EXECUTING: "Executing",
  REASONING: "Reasoning",
  VERIFYING: "Verifying",
  REPLANNING: "Replanning",
  SYNTHESIZING: "Synthesizing",
};

export function PhaseTracker({ stage, done }: { stage: Stage | null; done: boolean }) {
  const index = stage && stage !== "DONE" ? STAGES.indexOf(stage) : done ? STAGES.length : -1;

  return (
    <div className="panel">
      <h2>Phase</h2>
      <div className="phases">
        {STAGES.map((name, position) => {
          const isDone = position < index;
          const isActive = position === index && !done;
          const className = isDone ? "phase done" : isActive ? "phase active" : "phase";
          // The glyph carries the state as well as the colour does.
          const marker = isDone ? "✓" : isActive ? "●" : "○";
          return (
            <div key={name} className={className}>
              <span className="marker">{marker}</span>
              <span>{STAGE_LABEL[name]}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function TaskGraph({ graph }: { graph: TaskGraphResponse | null }) {
  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="panel">
        <h2>Task graph</h2>
        <div className="empty">No plan yet.</div>
      </div>
    );
  }

  const byId = new Map(graph.nodes.map((node) => [node.task_id, node]));
  const inserted = graph.nodes.filter((n) => n.inserted_by_replan).length;

  return (
    <div className="panel">
      <h2>
        Task graph
        <span className="count">
          {graph.nodes.length} tasks &middot; {graph.waves.length} waves
          {inserted > 0 ? ` · ${inserted} inserted mid-run` : ""}
        </span>
      </h2>
      {/* Waves come from the server: which tasks can run at once is a property of the
          graph, not a layout choice the client should re-derive. */}
      <div className="waves">
        {graph.waves.map((wave, position) => (
          <div className="wave" key={position}>
            <div className="wave-label">
              Wave {position}
              {wave.length > 1 ? ` · ${wave.length} parallel` : ""}
            </div>
            {wave.map((taskId) => {
              const node = byId.get(taskId);
              return node ? <TaskCard key={taskId} node={node} /> : null;
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function TaskCard({ node }: { node: TaskNode }) {
  const classes = ["task", node.status.toLowerCase()];
  if (node.inserted_by_replan) classes.push("inserted");

  return (
    <div className={classes.join(" ")} title={node.description}>
      <div className="tid">
        <span>{node.task_id}</span>
        <span>{node.status}</span>
      </div>
      <div className="ttype">{node.task_type}</div>
      {node.tool_id ? <div className="tool">{node.tool_id}</div> : null}
      {node.inserted_by_replan ? (
        <div className="inserted-tag">INSERTED BY REPLAN</div>
      ) : null}
    </div>
  );
}

export function FindingCard({
  finding,
  gaps = [],
  spawned = [],
}: {
  finding: Finding;
  /** Gaps detected against this finding. */
  gaps?: GapRecord[];
  /** Tasks the replanning loop inserted to close those gaps. */
  spawned?: TaskNode[];
}) {
  const [open, setOpen] = useState(false);
  const status = finding.verification?.status ?? "UNVERIFIED";
  const confidence = finding.confidence.value;
  const band = confidence >= 0.7 ? "high" : confidence >= 0.4 ? "medium" : "low";
  const unresolved = finding.evidence.filter((e) => e.resolution !== "RESOLVED").length;

  return (
    <div className={`finding ${status.toLowerCase()}`}>
      <div className="claim">{finding.claim}</div>

      <div className="badges">
        <span className="badge">{finding.classification}</span>
        <span className={`badge v-${status.toLowerCase()}`}>{status}</span>
        {finding.verification?.degraded ? (
          <span className="badge degraded" title={finding.verification.degraded_reason}>
            DEGRADED CHECK
          </span>
        ) : null}
        {/* The number, a band label and a bar. Colour is never the only cue. */}
        <span className="confidence">
          <span className="bar">
            <i className={band} style={{ width: `${Math.round(confidence * 100)}%` }} />
          </span>
          {confidence.toFixed(2)} {band}
        </span>
        <span className="spacer" />
        <button className="evidence-toggle" onClick={() => setOpen(!open)}>
          {open ? "hide" : "show"} evidence ({finding.evidence.length}
          {unresolved > 0 ? `, ${unresolved} unresolved` : ""})
        </button>
      </div>

      {open ? (
        <div className="evidence">
          {finding.evidence.length === 0 ? (
            <div className="dim">No evidence was cited for this claim.</div>
          ) : (
            finding.evidence.map((ref) => (
              <div className="evidence-row" key={ref.evidence_id}>
                <span className={`res ${ref.resolution.toLowerCase()}`}>
                  {ref.resolution === "RESOLVED"
                    ? "✓"
                    : ref.resolution === "PARTIAL"
                      ? "◐"
                      : "✗"}
                </span>
                <span className="loc">{formatLocator(ref)}</span>
                <span className={`res ${ref.resolution.toLowerCase()}`}>{ref.resolution}</span>
                {ref.resolution_note ? <span className="note">{ref.resolution_note}</span> : null}
              </div>
            ))
          )}

          {finding.verification && finding.verification.issues.length > 0 ? (
            <ul className="issues">
              {finding.verification.issues.map((issue, index) => (
                <li key={index}>
                  <code>{issue.issue_type}</code> {issue.description}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="hint mono">
            resolution {finding.confidence.resolution_rate.toFixed(2)} &middot; strength{" "}
            {finding.confidence.evidence_strength.toFixed(2)} &middot; agreement{" "}
            {finding.confidence.source_agreement.toFixed(2)} &middot; ceiling{" "}
            {finding.confidence.classification_ceiling.toFixed(2)}
          </div>
        </div>
      ) : null}

      {/* The evidence-gap moment. A gap names the specific absent element - never "more
          evidence needed", which would have failed at its job - and the task the loop
          inserted to go and find it. This is the plan changing, shown where it happened. */}
      {gaps.length > 0 ? (
        <div className="gap-moment">
          <div className="gap-head">
            {gaps.every((g) => g.resolved)
              ? "\u2713 evidence gap closed"
              : "\u26a0 evidence gap detected"}
          </div>
          {gaps.map((gap) => (
            <div className="gap-item" key={gap.gap_id}>
              <span className={`res ${gap.resolved ? "resolved" : "unresolved"}`}>
                {gap.resolved ? "\u2713" : "\u25cb"}
              </span>
              <span className="gap-type mono">{gap.gap_type}</span>
              <span className="gap-missing">missing: {gap.description}</span>
            </div>
          ))}
          {spawned.length > 0 ? (
            <div className="gap-spawned">
              the loop inserted{" "}
              {spawned.map((task, index) => (
                <span key={task.task_id}>
                  {index > 0 ? ", " : ""}
                  <span className="mono">{task.task_id}</span> ({task.task_type},{" "}
                  {task.status.toLowerCase()})
                </span>
              ))}{" "}
              to close it
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function formatLocator(ref: { locator: Finding["evidence"][number]["locator"] }): string {
  const { document_name, page, row } = ref.locator;
  if (page !== null) return `${document_name}:p${page}`;
  if (row !== null) return `${document_name}:r${row}`;
  return document_name;
}

export function Findings({
  findings,
  gaps = [],
  tasks = null,
}: {
  findings: Finding[];
  gaps?: GapRecord[];
  tasks?: TaskGraphResponse | null;
}) {
  const verified = findings.filter((f) => f.verification?.status === "SUPPORTED").length;

  // Gaps carry the finding they were detected against; inserted tasks carry the gap they were
  // created for. Joining them here is what turns three separate lists into one story.
  const gapsByFinding = new Map<string, GapRecord[]>();
  for (const gap of gaps) {
    const existing = gapsByFinding.get(gap.finding_id);
    if (existing) existing.push(gap);
    else gapsByFinding.set(gap.finding_id, [gap]);
  }
  const insertedTasks = (tasks?.nodes ?? []).filter((node) => node.inserted_by_replan);

  return (
    <div className="panel">
      <h2>
        Findings
        <span className="count">
          {findings.length === 0
            ? "none"
            : `${findings.length} · ${verified} verified`}
        </span>
      </h2>
      <div className="panel-body">
        {findings.length === 0 ? (
          <div className="dim">
            No findings. On an objective with nothing to find, this is the correct answer -
            the engine does not invent one to fill the space.
          </div>
        ) : (
          findings.map((f) => (
            <FindingCard
              key={f.finding_id}
              finding={f}
              gaps={gapsByFinding.get(f.finding_id) ?? []}
              spawned={insertedTasks}
            />
          ))
        )}
      </div>
    </div>
  );
}

export function Gaps({ gaps }: { gaps: GapRecord[] }) {
  if (gaps.length === 0) return null;
  const open = gaps.filter((g) => !g.resolved);

  return (
    <div className="panel">
      <h2>
        Evidence gaps
        <span className="count">
          {gaps.length} detected &middot; {gaps.length - open.length} closed
        </span>
      </h2>
      <div className="panel-body">
        {gaps.map((gap) => (
          <div className="evidence-row" key={gap.gap_id}>
            <span className={`res ${gap.resolved ? "resolved" : "unresolved"}`}>
              {gap.resolved ? "✓" : "○"}
            </span>
            <span className="loc">{gap.gap_type}</span>
            <span className="note">{gap.description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const PHASE_EVENTS = new Set([
  "RUN_STARTED",
  "INTENT_CREATED",
  "PLAN_CREATED",
  "TASK_GRAPH_CREATED",
  "REASONING_STARTED",
  "VERIFICATION_STARTED",
  "REPLAN_STARTED",
  "SYNTHESIS_STARTED",
  "RUN_COMPLETED",
]);

const BAD_EVENTS = new Set(["TASK_FAILED", "RUN_FAILED", "FINDING_REJECTED"]);

export function EventTimeline({ events }: { events: EventRecord[] }) {
  return (
    <div className="panel">
      <h2>
        Execution trace
        <span className="count">{events.length} events</span>
      </h2>
      {events.length === 0 ? (
        <div className="empty">Waiting for the run to start.</div>
      ) : (
        <div className="timeline">
          {events.map((event) => {
            const classes = ["event"];
            if (PHASE_EVENTS.has(event.event_type)) classes.push("phase-boundary");
            if (BAD_EVENTS.has(event.event_type)) classes.push("bad");
            return (
              <div className={classes.join(" ")} key={event.event_id}>
                {/* Offsets are relative to RUN_STARTED, which is what makes two traces
                    comparable. Wall-clock timestamps would not be. */}
                <span className="t">{formatOffset(event.t_offset_ms)}</span>
                <span className="kind">{event.event_type}</span>
                <span className="detail">{summarise(event)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatOffset(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}.${String(
    Math.floor((ms % 1000) / 100),
  )}`;
}

/** A one-line gloss. Operational fields only - model deliberation is never exposed. */
function summarise(event: EventRecord): string {
  const p = event.payload;
  const parts: string[] = [];
  if (event.task_id) parts.push(event.task_id);
  for (const key of ["task_type", "tool", "claim", "status", "classification", "reason", "goal"]) {
    const value = p[key];
    if (typeof value === "string" && value) parts.push(value);
  }
  if (typeof p["latency_ms"] === "number") parts.push(`${String(p["latency_ms"])}ms`);
  return parts.join(" · ").slice(0, 120);
}

export function Report({ report }: { report: FinalReport | null }) {
  if (!report) return null;

  return (
    <div className="panel">
      <h2>
        Report
        <span className="count">
          overall confidence {report.overall_confidence.toFixed(2)} &middot;{" "}
          {report.verified_findings.length} verified, {report.uncertain_findings.length} uncertain,{" "}
          {report.rejected_findings.length} rejected
        </span>
      </h2>
      {report.sections.map((section, index) => (
        <div className="report-section" key={index}>
          <h3>{section.heading}</h3>
          {section.narrative ? <p>{section.narrative}</p> : null}
          {section.items.length > 0 ? (
            <ul>
              {section.items.map((item, itemIndex) => (
                <li key={itemIndex}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function ExecutionStats({ report }: { report: FinalReport | null }) {
  if (!report) return null;
  const e = report.execution;
  const cells: [string, number | string][] = [
    ["tasks planned", e.tasks_planned],
    ["completed", e.tasks_completed],
    ["failed", e.tasks_failed],
    ["tool calls", e.tool_calls],
    ["documents", e.documents_processed],
    ["replans", e.replan_iterations],
    ["gaps detected", e.gaps_detected],
    ["gaps closed", e.gaps_resolved],
  ];

  return (
    <div className="panel">
      <h2>
        Execution
        <span className="count">every figure counted from the run, not described</span>
      </h2>
      <div className="stats">
        {cells.map(([label, value]) => (
          <div className="stat" key={label}>
            <div className="v">{value}</div>
            <div className="k">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
