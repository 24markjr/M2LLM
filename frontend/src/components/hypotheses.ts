/**
 * Competing explanations as the console shows them (Phase 47). Pure, so they are tested without
 * rendering.
 */

import type { Hypothesis, HypothesisSet } from "../api/types";
import { newMissionLink } from "./workspaces";

/** The document a locator names: "notes.txt:r5" -> "notes.txt", "Timeline 2.pdf:p3" -> "Timeline 2.pdf". */
export function documentOf(locator: string): string {
  const match = /^(.*?):[rpc]?\d+$/.exec(locator.trim());
  return match?.[1] ?? locator;
}

/** New Mission, filled in to test one open explanation against the lines its search found, in the
 * same case. A lead becomes evidence only through an investigation of its own. */
export function testLink(hypothesis: Hypothesis, caseId?: string): string {
  const leads = hypothesis.next_evidence?.leads ?? [];
  const documents = [...new Set(leads.map((lead) => documentOf(lead.locator)))];
  const decide = hypothesis.decisive_evidence ? ` Look for: ${hypothesis.decisive_evidence}.` : "";
  return newMissionLink({
    objective: `Does the evidence support this explanation: ${hypothesis.statement}${decide}`,
    documents,
    ...(caseId ? { caseId } : {}),
  });
}

/** One line for the panel heading: determined, open, or why there are none. */
export function hypothesesHeadline(set: HypothesisSet | null | undefined): string {
  if (!set) return "";
  if (set.skipped_reason) return `Not run: ${set.skipped_reason}`;
  return set.summary;
}

/** The net support as a reader should see it: "+0.90 (0.90 for, 0.00 against)". */
export function supportText(hypothesis: Hypothesis): string {
  const net = hypothesis.support - hypothesis.against;
  return `${net >= 0 ? "+" : "−"}${Math.abs(net).toFixed(2)} (${hypothesis.support.toFixed(2)} for, ${hypothesis.against.toFixed(2)} against)`;
}
