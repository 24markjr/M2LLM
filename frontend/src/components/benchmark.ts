/** The benchmark as the console shows it (Phase B1). Pure, so it is tested. */

import type { BenchmarkScore } from "../api/types";

export function systemLabel(system: string): string {
  if (system === "jarvis") return "JARVIS";
  if (system === "plain") return "Plain model";
  const [, model] = system.split(":");
  return model ? `${model} (frontier)` : system;
}

/** One scenario's result for one system, in a few characters. */
export function scoreCell(r: BenchmarkScore): { text: string; alarm: boolean } {
  if (r.error) return { text: `failed: ${r.error}`, alarm: false };
  const parts: string[] = [];
  if (r.correct !== null) parts.push(`${Math.round(r.correct * 100)}% facts`);
  if (r.sentences) parts.push(`${r.supported}/${r.sentences} supported`);
  if (r.false_alarm !== null) parts.push(r.false_alarm ? "false alarm" : "no false alarm");
  if (r.invented.length) parts.push(`${r.invented.length} invented`);
  return { text: parts.join(" · ") || "no answer", alarm: r.false_alarm === true };
}
