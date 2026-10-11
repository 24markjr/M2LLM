/**
 * Competing explanations (Phase 47): ranked by support computed from the verified findings, each
 * with the findings for and against it, what would decide it, and the next evidence - lines to read
 * (with an investigation to test them) or a request for what a person must provide.
 */

import type { HypothesisSet } from "../api/types";
import { hypothesesHeadline, supportText, testLink } from "./hypotheses";

export function Hypotheses({ set, caseId }: { set: HypothesisSet | null | undefined; caseId?: string | undefined }) {
  if (!set || (set.skipped_reason && set.hypotheses.length === 0 && set.skipped_reason.startsWith("the objective"))) {
    // Not an explanation question: nothing to show, and nothing missing.
    return null;
  }
  return (
    <div className="panel">
      <h2>
        Competing explanations
        <span className="count">
          {set.hypotheses.length
            ? `${set.hypotheses.length} · ${set.determined ? "determined" : `${set.hypotheses.filter((h) => h.status === "OPEN").length} open`}`
            : "none"}
        </span>
      </h2>
      <div className="panel-body">
        <div className={set.determined ? "hint" : "notice warn"}>{hypothesesHeadline(set)}</div>
        {set.hypotheses.map((h) => (
          <div className={`finding hyp-${h.status.toLowerCase()}`} key={h.hypothesis_id}>
            <div className="claim">
              <span className="mono dim">{h.hypothesis_id}</span> {h.statement}
            </div>
            <div className="badges">
              <span className={`badge hyp ${h.status.toLowerCase()}`} title={h.status_reason}>
                {h.status}
              </span>
              <span className="mono" title="Computed from the verified findings' confidence, never asked of the model">
                support {supportText(h)}
              </span>
            </div>
            {h.supporting.length || h.contradicting.length ? (
              <div className="dim">
                {h.supporting.length ? `for: ${h.supporting.map((r) => r.finding_id).join(", ")}` : ""}
                {h.supporting.length && h.contradicting.length ? " · " : ""}
                {h.contradicting.length ? `against: ${h.contradicting.map((r) => r.finding_id).join(", ")}` : ""}
              </div>
            ) : (
              <div className="dim">No verified finding bears on it.</div>
            )}
            {h.decisive_evidence ? <div>Would decide it: {h.decisive_evidence}</div> : null}
            {h.next_evidence ? (
              <div className="gap-moment">
                <div className="gap-head">
                  {h.next_evidence.kind === "SEARCH" ? "Next evidence: lines to read" : "Needed from you"}
                </div>
                <div>{h.next_evidence.text}</div>
                {h.next_evidence.leads.map((lead) => (
                  <div className="gap-item" key={lead.locator}>
                    <span className="mono">{lead.locator}</span> <span className="dim">{lead.text}</span>
                  </div>
                ))}
                {h.next_evidence.kind === "SEARCH" ? (
                  <a className="button" href={testLink(h, caseId)}>
                    investigate these lines
                  </a>
                ) : (
                  <a className="button" href="#/documents">
                    add the evidence
                  </a>
                )}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
