/**
 * A reviewer's decision on one finding (Phase 50): approve, reject (with a reason, optionally
 * starting a follow-up investigation), or modify (with the reworded claim). Every decision is a new
 * record; the history stays visible.
 */

import { useState } from "react";

import { api } from "../api/client";
import type { FindingReview, ReviewState } from "../api/types";
import { reviewSummary } from "./review";

export function ReviewPanel({ runId, review }: { runId?: string | undefined; review: FindingReview | undefined }) {
  const [current, setCurrent] = useState<FindingReview | undefined>(undefined);
  const [followUp, setFollowUp] = useState("");
  const [error, setError] = useState("");
  const shown = current ?? review;
  if (!runId || !shown) return null;

  const decide = (state: ReviewState) => {
    let reason = "";
    let modifiedClaim = "";
    let replan = false;
    if (state !== "APPROVED") {
      reason = window.prompt(state === "REJECTED" ? "Why is it rejected?" : "Why is it reworded?") ?? "";
      if (!reason.trim()) return;
    }
    if (state === "MODIFIED") {
      modifiedClaim = window.prompt("The claim as it should read:", shown.claim) ?? "";
      if (!modifiedClaim.trim()) return;
    }
    if (state === "REJECTED") {
      replan = window.confirm("Start a follow-up investigation of the same question?");
    }
    api
      .reviewFinding(runId, shown.finding_id, { state, reason, modified_claim: modifiedClaim, replan })
      .then((response) => {
        setCurrent(response.review);
        setFollowUp(response.follow_up_run_id);
      })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  return (
    <div className="review">
      <div className="dim">{reviewSummary(shown)}</div>
      <div className="row">
        <button onClick={() => decide("APPROVED")}>Approve</button>
        <button onClick={() => decide("MODIFIED")}>Modify</button>
        <button onClick={() => decide("REJECTED")}>Reject</button>
      </div>
      {shown.history.length > 0 ? (
        <ol className="chain-steps">
          {shown.history.map((d) => (
            <li key={d.decision_id}>
              {d.state} by {d.reviewer} {d.reason ? <span className="dim">- {d.reason}</span> : null}
              {d.modified_claim ? <div className="dim">now reads: {d.modified_claim}</div> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {followUp ? (
        <a className="button" href={`#/mission/${followUp}`}>
          follow-up investigation {followUp}
        </a>
      ) : null}
      {error ? <div className="notice error">{error}</div> : null}
    </div>
  );
}
