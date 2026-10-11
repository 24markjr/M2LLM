/**
 * The Evidence Locker (Phase 43), the pure part: links, labels and the lookups that tie a
 * finding's citation to the evidence item it rests on. Kept free of React so it is tested directly.
 */

export const EVIDENCE_ID = /^EV-\d{6,}$/;

/** The Evidence Locker, or one item in it. */
export function evidenceLink(evidenceId?: string): string {
  return evidenceId && EVIDENCE_ID.test(evidenceId) ? `#/evidence/${evidenceId}` : "#/evidence";
}

/** `#/evidence/EV-000012` -> "EV-000012"; anything else -> "". */
export function evidenceIdFromHash(hash: string): string {
  const match = /^#\/evidence\/(EV-\d{6,})$/.exec(hash.split("?")[0] ?? hash);
  return match?.[1] ?? "";
}

/**
 * The evidence item a citation rests on, from the mission's name -> id map. A citation names a
 * document (`report.txt:r12`, or the document id itself); the map was fixed when the mission was
 * admitted, so the link is to the exact version the mission read, not the newest one.
 */
export function evidenceForCitation(
  evidence: Record<string, string> | undefined,
  documentName: string,
): string | undefined {
  if (!evidence) return undefined;
  return evidence[documentName] ?? evidence[documentName.split(":")[0] ?? documentName];
}

/** What each custody action means, in words a reviewer reads without a glossary. */
const CUSTODY_WORDS: Record<string, string> = {
  ACQUIRED: "Acquired",
  HASHED: "Fingerprinted (SHA-256)",
  STORED: "Original stored, write-once",
  IMPORTED: "Registered (earlier history unknown)",
  PARSED: "Read into citable lines",
  PARSE_FAILED: "Could not be read",
  UNDERSTOOD: "Understood (read, seen or heard)",
  INDEXED: "Indexed for search by meaning",
  ANALYSED: "Read by a mission",
  CITED: "Cited by a finding",
  REPORTED: "Included in a report",
  VERIFIED: "Integrity verified",
  INTEGRITY_FAILED: "Integrity check FAILED",
  METADATA_CHANGED: "Details changed",
};

export function custodyLabel(action: string): string {
  return CUSTODY_WORDS[action] ?? action;
}

/** The detail worth one line in a timeline, chosen per action; the rest stays in the raw record. */
/** A source authority tier id in words (Phase 45): "CORRESPONDENCE" -> "correspondence". */
export function authorityWords(tier: string | undefined): string {
  if (!tier || tier === "UNASSESSED") return "not assessed";
  return tier.replace(/_/g, " ").toLowerCase();
}

export function custodySummary(action: string, details: Record<string, unknown>): string {
  const text = (key: string) => (details[key] === undefined ? "" : String(details[key]));
  switch (action) {
    case "ACQUIRED":
      return `${text("name")}, ${text("bytes")} bytes`;
    case "PARSED":
      return `${text("parser")}, ${text("lines")} line(s)${details.has_text === false ? ", no text yet" : ""}`;
    case "INDEXED":
      return `workspace ${text("workspace")}, ${text("chunks")} chunk(s) in ${text("store")}`;
    case "ANALYSED":
      return `mission ${text("run_id")}`;
    case "CITED":
      return `${text("finding_id")} at ${text("locator")} (mission ${text("run_id")})`;
    case "INTEGRITY_FAILED":
    case "PARSE_FAILED":
    case "IMPORTED":
      return text("reason");
    case "METADATA_CHANGED":
      return Object.entries(details)
        .map(([field, change]) => {
          // A change is {from, to}; anything else (a reason, Phase 45) is shown as it is.
          if (typeof change !== "object" || change === null) return `${field}: ${String(change)}`;
          const c = change as { from?: unknown; to?: unknown };
          return `${field}: ${String(c.from ?? "")} → ${String(c.to ?? "")}`;
        })
        .join("; ");
    default:
      return "";
  }
}

export const CLASSIFICATIONS = ["UNCLASSIFIED", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] as const;
