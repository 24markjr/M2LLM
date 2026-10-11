/**
 * Challenge JARVIS (Phase 48): ask for a counter-analysis of one finding. The finding is not
 * changed; the challenge is shown beside it - outcome, the lines that disagree and how authoritative
 * each is, whether its own line holds it, the verifier's view of the counter lines, and confidence
 * before and after.
 */

import { useState } from "react";

import { api } from "../api/client";
import type { ChallengeResult } from "../api/types";
import { challengeDelta } from "./challenge";

export function ChallengePanel({ runId, findingId }: { runId?: string | undefined; findingId: string }) {
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!runId) return null;

  const run = () => {
    setBusy(true);
    setError("");
    api
      .challengeFinding(runId, findingId)
      .then(setResult)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="challenge">
      <button className="evidence-toggle" onClick={run} disabled={busy}>
        {busy ? "Challenging." : result ? "challenge again" : "challenge this finding"}
      </button>
      {error ? <div className="notice error">{error}</div> : null}
      {result ? (
        <div className={`challenge-result ${result.outcome.toLowerCase()}`}>
          <div>
            <span className={`badge challenge ${result.outcome.toLowerCase()}`}>{result.outcome}</span>{" "}
            <span className="mono">{challengeDelta(result)}</span>
          </div>
          <div>{result.summary}</div>
          {result.counter_evidence.map((c) => (
            <div className="gap-item" key={c.locator}>
              <span className="mono">{c.locator}</span> <span className="badge authority">{c.authority}</span>{" "}
              {c.stronger ? <span className="badge">stronger source</span> : null} {c.reason}
              <div className="dim">{c.text}</div>
            </div>
          ))}
          <div className="dim">its own lines: {result.own_lines}</div>
          <div className="dim">negated claim: {result.negation_check}</div>
          <div className="dim">
            {result.authority_note} · challenged by {result.challenged_by}
          </div>
        </div>
      ) : null}
    </div>
  );
}
