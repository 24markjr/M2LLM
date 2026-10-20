/**
 * Proof (Phase U7), apart from React: the receipt as plain text, and the comparison in words.
 *
 * Every figure here is read from the receipt or the comparison the server counted. The words
 * describe the counts; they never grade them ("better", "worse") - the reader does that.
 */

import type { AnswerTally, Comparison, Receipt } from "../api/types";

export function shortHash(hash: string): string {
  return hash.length > 16 ? `${hash.slice(0, 8)}…${hash.slice(-8)}` : hash;
}

/** "3 of 4 sentences supported by a line in the files". */
export function tallyLine(t: AnswerTally): string {
  if (t.sentences === 0) return "No answer to check.";
  const parts = [`${t.supported} of ${t.sentences} sentence(s) supported by a line in the files`];
  if (t.partial) parts.push(`${t.partial} partly`);
  if (t.contradicted) parts.push(`${t.contradicted} contradicted`);
  if (t.unsupported) parts.push(`${t.unsupported} unsupported`);
  if (t.insufficient) parts.push(`${t.insufficient} without enough evidence`);
  return parts.join("; ");
}

/** The share of sentences fully supported, 0-1; null with nothing to check. */
export function supportedShare(t: AnswerTally): number | null {
  return t.sentences ? t.supported / t.sentences : null;
}

/** What differs between the two answers, as counts. */
export function differences(c: Comparison): string[] {
  const out: string[] = [];
  const pct = (t: AnswerTally) => {
    const s = supportedShare(t);
    return s === null ? "nothing to check" : `${Math.round(s * 100)}% of sentences supported`;
  };
  out.push(`Plain model: ${pct(c.plain.tally)}. JARVIS: ${pct(c.jarvis.tally)}.`);
  const figures = (n: number) => (n === 1 ? "1 date or figure" : `${n} dates or figures`);
  out.push(
    `Stated but found in no file: plain model ${figures(c.plain.ungrounded.length)}, JARVIS ${figures(c.jarvis.ungrounded.length)}.`,
  );
  out.push(
    `Findings with a resolved citation behind the answer: plain model none (it cites nothing checkable), JARVIS ${c.jarvis.cited_findings}.`,
  );
  if (c.truncated) out.push("The files were longer than the plain model's prompt allows, so it saw only the first part of them.");
  return out;
}

function when(at: string | null): string {
  return at ? new Date(at).toISOString() : "-";
}

/** The receipt as plain text: what a printed copy carries. */
export function receiptText(r: Receipt): string {
  const lines = [
    "JARVIS VERIFICATION RECEIPT",
    `Run:        ${r.run_id}`,
    `Question:   ${r.question}`,
    `Model:      ${r.model}`,
    `Prompts:    ${Object.entries(r.prompt_versions).map(([k, v]) => `${k} v${v}`).join(", ") || "-"}`,
    `Started:    ${when(r.started_at)}`,
    `Finished:   ${when(r.finished_at)}`,
    `Tasks:      ${r.tasks_completed} of ${r.tasks_planned} completed; ${r.gaps_open} gap(s) open`,
    "",
    "FILES (SHA-256 of the text as read)",
    ...r.documents.map((d) => `  ${d.sha256}  ${d.name} (${d.characters} chars)${d.evidence_id ? ` evidence ${d.evidence_id}` : ""}`),
    "",
    "FINDINGS",
    ...r.findings.map(
      (f) =>
        `  ${f.finding_id}  ${f.verification}${f.degraded ? " (degraded)" : ""}  ${f.citations_resolved}/${f.citations} citation(s) resolved  ${Math.round(f.confidence * 100)}%  ${f.claim}`,
    ),
    "",
    `ANSWER     ${tallyLine(r.answer)}`,
    "",
    `Receipt hash (SHA-256 over every field above): ${r.receipt_hash}`,
  ];
  return lines.join("\n");
}
