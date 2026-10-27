/**
 * The investigation conversation (v4 Phase 3), as the case page shows it. Pure, so it is tested
 * without rendering.
 */

import type { StopReason, ToolStep, Turn } from "../api/types";

/** Why an answer stopped, in words a person reads - never silent about a budget or a failure. */
export function stopLabel(reason: StopReason | null): string {
  switch (reason) {
    case "ANSWERED":
      return "";
    case "ASKED_USER":
      return "needs your answer";
    case "STEP_LIMIT":
      return "answered from what five lookups found";
    case "RECHECKED":
      return "re-checked";
    case "FAILED":
      return "could not answer";
    default:
      return "";
  }
}

/** "searched 2×, read 1 passage, calculated" - what the answer rests on, in one line. */
export function toolSummary(steps: ToolStep[]): string {
  const words: Record<string, [string, string]> = {
    search_evidence: ["searched", "searched"],
    read_span: ["read 1 passage", "read {n} passages"],
    query_findings: ["looked up findings", "looked up findings {n}×"],
    calculate: ["calculated", "calculated {n}×"],
    compare_values: ["compared values", "compared values {n}×"],
  };
  const counts = new Map<string, number>();
  for (const step of steps) counts.set(step.tool, (counts.get(step.tool) ?? 0) + 1);
  return [...counts.entries()]
    .map(([tool, n]) => {
      const [one, many] = words[tool] ?? [tool, `${tool} {n}×`];
      if (tool === "search_evidence") return n === 1 ? one : `${one} ${n}×`;
      return (n === 1 ? one : many).replace("{n}", String(n));
    })
    .join(", ");
}

/** The question the assistant is waiting on, if its last turn asked one. */
export function pendingQuestion(turns: Turn[]): string {
  const last = turns.at(-1);
  return last?.role === "assistant" && last.stop_reason === "ASKED_USER" ? last.question : "";
}
