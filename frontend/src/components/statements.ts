/**
 * Statement types and source authority as the console shows them (Phase 45). Pure, so they are
 * tested without rendering.
 */

import type { Finding, StatementType } from "../api/types";
import { authorityWords } from "./evidence";

/** Every resolved citation in one document (BUG-030): computed here as the engine computes it. */
export function singleSource(finding: Finding): boolean {
  const documents = new Set(
    finding.evidence.filter((e) => e.resolution === "RESOLVED").map((e) => e.locator.document_id),
  );
  return documents.size === 1;
}

/** The finding's statement type (Phase 45). A finding stored before Phase 45 has none, and shows
 * what its evidence alone supports: one document is a source claim, never a fact. */
export function statementType(finding: Finding): StatementType {
  if (finding.statement_type && finding.statement_type !== "UNKNOWN") return finding.statement_type;
  const resolved = finding.evidence.filter((e) => e.resolution === "RESOLVED");
  if (resolved.length === 0) return "UNKNOWN";
  if (resolved.length < finding.evidence.length) return "HYPOTHESIS";
  return singleSource(finding) ? "SOURCE_CLAIM" : finding.classification === "FACT" ? "FACT" : "INFERENCE";
}

/** "SOURCE CLAIM", or a proposed kind with what it rests on: "RISK on SOURCE CLAIM". */
export function statementLabel(finding: Finding): string {
  const kind = statementType(finding);
  const basis = finding.statement_basis;
  const words = (t: string) => t.replace(/_/g, " ");
  if (!basis || basis === kind || kind === "CONTRADICTION") return words(kind);
  return `${words(kind)} on ${words(basis)}`;
}

const STATEMENT_HELP: Record<StatementType, string> = {
  FACT: "Stated by two or more documents, every citation resolved",
  SOURCE_CLAIM: "Stated by one document: true to its source, not corroborated",
  INFERENCE: "Drawn across documents with a step none of them states outright",
  HYPOTHESIS: "Partly supported: some of what it cites did not resolve",
  CONTRADICTION: "Two evidenced values that cannot both be true; each side's authority is shown, neither is chosen",
  RISK: "Proposed as a risk by the model; the basis shows what it rests on",
  RECOMMENDATION: "Proposed as a recommendation by the model; the basis shows what it rests on",
  OBSERVATION: "Proposed as an observation by the model; the basis shows what it rests on",
  UNKNOWN: "Nothing it cites resolved",
};

export function statementHelp(finding: Finding): string {
  const help = STATEMENT_HELP[statementType(finding)];
  return finding.proposed_type ? `${help}. The model proposed: ${finding.proposed_type}` : help;
}

/** A tier id in words ("SOURCE_CLAIM" style ids are not for readers). */
export function authorityText(tier: string | undefined): string {
  return `authority: ${authorityWords(tier)}`;
}
