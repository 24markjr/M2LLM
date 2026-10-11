import { describe, expect, it } from "vitest";

import type { InvestigationReport } from "../api/types";
import { reportCounts } from "./investigationReport";

describe("investigation report (Phase 51)", () => {
  it("counts what is established, awaiting review and not established", () => {
    const finding = { finding_id: "F-001" } as InvestigationReport["established"][number];
    const report = {
      established: [finding, finding],
      awaiting_review: [finding],
      not_established: [],
    } as unknown as InvestigationReport;
    expect(reportCounts(report)).toBe("2 established · 1 awaiting review · 0 not established");
  });
});
