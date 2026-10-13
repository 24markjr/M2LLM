/**
 * Composer modes (Phase U4). A mode shapes the question the engine receives - it does not switch to a
 * different engine. Every mode runs the same investigation: plan, read, verify, cite. The wording
 * tells the intent engine which operations to plan (comparison, timeline, security analysis), and
 * the Security logs mode also marks a new case as CYBER (Phase 52: log analysis and ATT&CK).
 */

export type Mode = "investigate" | "compare" | "timeline" | "security";

export interface ModeInfo {
  id: Mode;
  label: string;
  hint: string;
  placeholder: string;
}

export const MODES: ModeInfo[] = [
  {
    id: "investigate",
    label: "Investigate",
    hint: "Plan, read, verify and cite; finds what is missing and keeps looking",
    placeholder: "What do you need to find out?",
  },
  {
    id: "compare",
    label: "Compare",
    hint: "Where the documents agree, and where they contradict each other",
    placeholder: "What should the documents be compared on?",
  },
  {
    id: "timeline",
    label: "Timeline",
    hint: "Events in order, with conflicting dates marked",
    placeholder: "Whose or what timeline?",
  },
  {
    id: "security",
    label: "Security logs",
    hint: "Indicators, decoded commands, ATT&CK techniques, the attack path",
    placeholder: "What should the logs be examined for?",
  },
];

const PREFIX: Record<Mode, string> = {
  investigate: "",
  compare: "Compare the attached documents: where do they agree, and where do they contradict each other? ",
  timeline: "Build a timeline of the events in the attached documents, and note any dates that conflict. ",
  security: "Examine the attached security logs for malicious activity. ",
};

/** The objective sent to the engine: the question, with the mode's framing in front of it. */
export function objectiveFor(mode: Mode, question: string): string {
  const text = question.trim();
  if (!text) return "";
  return mode === "investigate" ? text : `${PREFIX[mode]}${text}`;
}

/** A case title from the question: its first sentence, at most 80 characters. */
export function caseTitleFor(question: string): string {
  const first = (question.trim().split(/(?<=[.?!])\s/)[0] ?? "").trim();
  const title = first.length > 80 ? `${first.slice(0, 77).trimEnd()}...` : first;
  return title.length >= 3 ? title : "Untitled investigation";
}

/** The engine needs 8 to 2,000 characters; the reason to show, or "" when the question is usable. */
export function questionProblem(question: string, mode: Mode = "investigate"): string {
  const n = question.trim().length;
  if (n === 0) return "Ask a question first.";
  if (n < 8) return "A little more detail, please - at least 8 characters.";
  if (objectiveFor(mode, question).length > 2000) return "Shorter, please - the engine takes at most 2,000 characters.";
  return "";
}
