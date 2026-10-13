/**
 * What a statement's status looks like (Phase U2): the "status underline" of the redesign.
 *
 * Every answer marks each sentence verified, inferred, not established or unknown. The mark is a
 * colour, a line style and a glyph, and the word is always available to a screen reader and on
 * hover, so nobody has to tell colours apart.
 */

export type Status = "verified" | "inferred" | "unsupported" | "unknown";

export interface StatusMeta {
  label: string;
  glyph: string;
  description: string;
}

export const STATUS: Record<Status, StatusMeta> = {
  verified: {
    label: "Verified",
    glyph: "✓",
    description: "Its cited lines say this, and an independent check agreed.",
  },
  inferred: {
    label: "Inferred",
    glyph: "≈",
    description: "Reasoned from cited lines that do not say it in so many words.",
  },
  unsupported: {
    label: "Not established",
    glyph: "✕",
    description: "The cited lines do not support it. Shown so it is not mistaken for a finding.",
  },
  unknown: {
    label: "Unknown",
    glyph: "?",
    description: "Not checked yet, or nothing in the evidence decides it.",
  },
};

/** A verification status from the API (`VerificationStatus`) as the mark to show. */
export function statusOf(verification: string | null | undefined): Status {
  switch ((verification ?? "").toUpperCase()) {
    case "SUPPORTED":
      return "verified";
    case "PARTIALLY_SUPPORTED":
      return "inferred";
    case "UNSUPPORTED":
    case "CONTRADICTED":
      return "unsupported";
    default: // INCONCLUSIVE, or not verified yet
      return "unknown";
  }
}
