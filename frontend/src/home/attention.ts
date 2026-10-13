/**
 * "Needs your attention" (Phase U4): what on the home page is waiting for a person, from the
 * investigations the engine holds. Running ones first, then finished ones with findings that did not
 * all verify, then ones with questions the evidence left open. At most six.
 */

export interface MissionLike {
  run_id: string;
  objective: string;
  status: string;
  created_at: string;
  finished_at?: string | null;
  finding_count: number;
  verified_count: number;
  unresolved_gap_count: number;
  case_id?: string;
}

export interface AttentionItem {
  key: string;
  kind: "running" | "review" | "open";
  title: string;
  detail: string;
  href: string;
}

const RECENT_DAYS = 7;

export function attentionItems(missions: MissionLike[], now: Date, limit = 6): AttentionItem[] {
  const since = now.getTime() - RECENT_DAYS * 24 * 60 * 60 * 1000;
  const recent = (m: MissionLike) => Date.parse(m.finished_at ?? m.created_at) >= since;
  const href = (m: MissionLike) => `#/mission/${m.run_id}`;
  const items: AttentionItem[] = [];

  for (const m of missions) {
    if (m.status === "RUNNING" || m.status === "PENDING") {
      items.push({ key: `run-${m.run_id}`, kind: "running", title: m.objective, detail: "Running now", href: href(m) });
    }
  }
  for (const m of missions) {
    const unverified = m.finding_count - m.verified_count;
    if (m.status === "COMPLETED" && recent(m) && unverified > 0) {
      items.push({
        key: `review-${m.run_id}`,
        kind: "review",
        title: m.objective,
        detail: `${unverified} of ${m.finding_count} finding(s) not verified - worth a look`,
        href: href(m),
      });
    }
  }
  for (const m of missions) {
    if (m.status === "COMPLETED" && recent(m) && m.unresolved_gap_count > 0) {
      items.push({
        key: `open-${m.run_id}`,
        kind: "open",
        title: m.objective,
        detail: `${m.unresolved_gap_count} question(s) the evidence left open`,
        href: href(m),
      });
    }
  }
  return items.slice(0, limit);
}
