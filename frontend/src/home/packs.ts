/**
 * Domain packs (Phase U4): one engine, the wording and defaults of a field.
 *
 * A pack sets the starter questions on the home page, the default mode and the default sensitivity
 * of files uploaded under it. It does not change how the engine reasons, verifies or cites; per-pack
 * entity types, report templates and severity rules are Phase B7. Starters with `files` attach real
 * example files from `.agent/fixtures/documents`, so each one runs as shown.
 */

import type { Mode } from "./modes";

export type Sensitivity = "UNCLASSIFIED" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED";

export interface Starter {
  question: string;
  files: string[];
  mode?: Mode;
}

export interface Pack {
  id: string;
  label: string;
  blurb: string;
  mode: Mode;
  sensitivity: Sensitivity;
  /** Shown under the composer while the pack is chosen. */
  notice?: string;
  starters: Starter[];
}

export const PACKS: Pack[] = [
  {
    id: "general",
    label: "General",
    blurb: "Any set of documents",
    mode: "investigate",
    sensitivity: "INTERNAL",
    starters: [
      {
        question: "Do the Aurora project reports contradict each other on the timeline or the finances?",
        files: ["aurora_project_report.txt", "aurora_financial_report.txt", "aurora_milestone_report.txt"],
      },
      { question: "Where do these documents agree, and where do they differ?", files: [], mode: "compare" },
    ],
  },
  {
    id: "investigation",
    label: "Investigation",
    blurb: "Statements, incidents, who did what when",
    mode: "investigate",
    sensitivity: "CONFIDENTIAL",
    starters: [
      {
        question: "When did shipment 4821 actually arrive, and do the statements agree?",
        files: [
          "shipment_report_a.txt",
          "shipment_report_b.txt",
          "shipment_witness_statement.txt",
          "shipment_driver_note.txt",
        ],
      },
      {
        question: "What caused the Lyra outage? Keep the explanations the evidence cannot decide open.",
        files: ["lyra_incident_log.txt", "lyra_change_record.txt", "lyra_facilities_note.txt"],
      },
    ],
  },
  {
    id: "finance",
    label: "Finance and audit",
    blurb: "Budgets, ledgers, approvals",
    mode: "investigate",
    sensitivity: "CONFIDENTIAL",
    starters: [
      {
        question: "Does the spending in the Orion ledger exceed what was approved?",
        files: ["orion_ledger.xlsx", "orion_budget_memo.docx", "orion_purchase_order.txt"],
      },
      {
        question: "When does Project Vega start, according to its most authoritative source?",
        files: ["vega_approved_budget_statement.txt", "vega_finance_summary.txt", "vega_draft_email.txt"],
      },
    ],
  },
  {
    id: "legal",
    label: "Legal",
    blurb: "Contracts, statements, evidence bundles",
    mode: "investigate",
    sensitivity: "CONFIDENTIAL",
    starters: [
      { question: "Do the witness statements contradict each other, and on what?", files: ["shipment_witness_statement.txt", "shipment_employee_statement.txt"], mode: "compare" },
      { question: "Which obligations in these contracts are time-bound, and are any already overdue?", files: [] },
    ],
  },
  {
    id: "healthcare",
    label: "Healthcare",
    blurb: "Record review and decision support",
    mode: "timeline",
    sensitivity: "CONFIDENTIAL",
    notice:
      "Record review and decision support only - not a diagnosis. Every statement is cited to the records; a clinician decides.",
    starters: [
      { question: "Build a timeline of this patient's medications and flag doses that overlap or conflict.", files: [], mode: "timeline" },
      { question: "Do the discharge summary and the lab results disagree anywhere?", files: [], mode: "compare" },
    ],
  },
  {
    id: "cyber",
    label: "Cyber",
    blurb: "Security logs, indicators, ATT&CK",
    mode: "security",
    sensitivity: "CONFIDENTIAL",
    starters: [
      {
        question: "Do these Windows logs show malicious PowerShell activity, and what did it contact?",
        files: ["cyber_ws12_security.xml"],
        mode: "security",
      },
      {
        question: "Determine how the svc_admin account moved between servers and what it ran on each.",
        files: ["cyber_lateral_movement.jsonl"],
        mode: "security",
      },
    ],
  },
];

export const PACK_KEY = "jarvis.pack";

export function packById(id: string | null | undefined): Pack {
  return PACKS.find((p) => p.id === id) ?? (PACKS[0] as Pack);
}
