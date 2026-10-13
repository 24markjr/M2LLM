/**
 * Composer modes (Phase U4). The question is sent as asked, with the mode. On the engine a mode makes
 * certain operations required in the plan, whatever the model proposes (`MODE_OPERATIONS` in the
 * intent engine): Compare - compare sources and detect contradictions; Timeline - extract the
 * timeline and detect inconsistencies; Security logs - entities, timeline, impact, and a new case is
 * CYBER (Phase 52: log analysis and ATT&CK). Every mode still plans, reads, verifies and cites.
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

/** What each mode makes required in the plan, in words (shown under the composer). */
export const MODE_PLANS: Record<Mode, string> = {
  investigate: "",
  compare: "The plan will compare the sources and look for contradictions.",
  timeline: "The plan will extract the timeline and look for dates that conflict.",
  security: "The plan will extract hosts, accounts and events in order, and assess the impact.",
};

/** A case title from the question: its first sentence, at most 80 characters. */
export function caseTitleFor(question: string): string {
  const first = (question.trim().split(/(?<=[.?!])\s/)[0] ?? "").trim();
  const title = first.length > 80 ? `${first.slice(0, 77).trimEnd()}...` : first;
  return title.length >= 3 ? title : "Untitled investigation";
}

/** The engine needs 8 to 2,000 characters; the reason to show, or "" when the question is usable. */
export function questionProblem(question: string): string {
  const n = question.trim().length;
  if (n === 0) return "Ask a question first.";
  if (n < 8) return "A little more detail, please - at least 8 characters.";
  if (n > 2000) return "Shorter, please - the engine takes at most 2,000 characters.";
  return "";
}
