/**
 * The proof card's numbers (demo readiness): what was checked, what held, what was caught - read
 * from the findings' own verdicts and the run's evidence record, never estimated.
 */

import type { Finding } from "../api/types";

export interface ProofTally {
  claims: number;
  verified: number;
  partly: number;
  caught: number;
  unproven: number;
  files: number;
  translated: number;
  seconds: number | null;
}

export function proofTally(
  findings: Finding[],
  evidence: Record<string, string>,
  translated: string[],
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): ProofTally {
  const status = (f: Finding) => f.verification?.status ?? "";
  const started = startedAt ? Date.parse(startedAt) : NaN;
  const finished = finishedAt ? Date.parse(finishedAt) : NaN;
  return {
    claims: findings.length,
    verified: findings.filter((f) => status(f) === "SUPPORTED").length,
    partly: findings.filter((f) => status(f) === "PARTIALLY_SUPPORTED").length,
    caught: findings.filter((f) => status(f) === "CONTRADICTED").length,
    unproven: findings.filter((f) => ["UNSUPPORTED", "INCONCLUSIVE", ""].includes(status(f))).length,
    files: Object.keys(evidence).length,
    translated: translated.length,
    seconds: Number.isFinite(started) && Number.isFinite(finished) ? Math.round((finished - started) / 1000) : null,
  };
}
