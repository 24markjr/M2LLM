/**
 * The plan as a person reads it (Phase 49): the objective, its workstreams, and each step with why
 * it is there, what it took in, what it did and what came out - then every time JARVIS changed its
 * plan, with what triggered it and why.
 */

import type { PlanTree } from "../api/types";
import { changeHeadline, planCounts } from "./planTree";

export function PlanChanges({ tree }: { tree: PlanTree | null | undefined }) {
  if (!tree || tree.changes.length === 0) return null;
  return (
    <div className="panel">
      <h2>
        JARVIS changed its plan <span className="count">{tree.changes.length} change(s)</span>
      </h2>
      <div className="panel-body">
        {tree.changes.map((change) => (
          <div className="gap-moment" key={change.revision}>
            <div className="gap-head">{changeHeadline(change)}</div>
            {change.added.map((step) => (
              <div className="gap-item" key={step.task_id}>
                <span className="mono">{step.task_id}</span> {step.label}
                <div className="dim">why: {step.why}</div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PlanTreePanel({ tree }: { tree: PlanTree | null | undefined }) {
  if (!tree) return null;
  const counts = planCounts(tree);
  return (
    <div className="panel">
      <h2>
        The plan{" "}
        <span className="count">
          {counts.steps} step(s){counts.added ? ` · ${counts.added} added during the run` : ""}
        </span>
      </h2>
      <div className="panel-body">
        <div className="hint">{tree.objective}</div>
        {tree.repairs.length ? (
          <div className="dim">repairs before it ran: {tree.repairs.join("; ")}</div>
        ) : null}
        {tree.workstreams.map((stream) => (
          <div className="workstream" key={stream.name}>
            <div className="why-head">{stream.name}</div>
            <ol className="chain-steps">
              {stream.steps.map((step) => (
                <li key={step.task_id}>
                  <span className={`badge s-${step.status.toLowerCase()}`}>{step.status}</span>{" "}
                  <span className="mono dim">{step.task_id}</span> {step.label}
                  {step.inserted_by_revision ? <span className="badge">added in revision {step.inserted_by_revision}</span> : null}
                  <div className="dim">why: {step.why}</div>
                  <div className="dim">
                    in: {step.inputs.join("; ") || "-"}
                    {step.action ? ` · did: ${step.action}` : ""}
                    {step.output ? ` · out: ${step.output}` : ""}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}
