/**
 * "Why this confidence?" and the evidence chain for one finding (Phase 46).
 *
 * The factor table comes from the finding itself, so it works in a replay too. The chain - each
 * citation with its Evidence Locker item, authority, the text read and what was extracted from it,
 * then reasoning, the verifiers and the conclusion - is fetched from the run when asked for.
 */

import { useState } from "react";

import { api } from "../api/client";
import type { Finding, FindingChain } from "../api/types";
import { confidenceSum, costs, factorRows, SCORE_NOTE } from "./confidence";
import { evidenceLink } from "./evidence";
import { graphSearchLink } from "./graph3d/investigation";

export function ConfidenceWhy({ finding, runId }: { finding: Finding; runId?: string | undefined }) {
  const [chain, setChain] = useState<FindingChain | null>(null);
  const [error, setError] = useState("");
  const rows = factorRows(finding.confidence);

  const loadChain = () => {
    if (!runId) return;
    api
      .getFindingChain(runId, finding.finding_id)
      .then(setChain)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  if (rows.length === 0) {
    // A confidence computed before Phase 46 has its components only.
    return (
      <div className="hint mono">
        resolution {finding.confidence.resolution_rate.toFixed(2)} &middot; strength{" "}
        {finding.confidence.evidence_strength.toFixed(2)} &middot; agreement{" "}
        {finding.confidence.source_agreement.toFixed(2)} &middot; ceiling{" "}
        {finding.confidence.classification_ceiling.toFixed(2)}
      </div>
    );
  }

  return (
    <div className="why">
      <div className="why-head" title={SCORE_NOTE}>
        Why {finding.confidence.value.toFixed(2)}? <span className="why-note">{SCORE_NOTE}</span>
      </div>
      <div className="mono why-sum">{confidenceSum(finding.confidence)}</div>
      <table className="metrics why-factors">
        <thead>
          <tr>
            <th>Factor</th>
            <th>Value</th>
            <th>Weight</th>
            <th>Adds</th>
            <th>Because</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className={row.assessed ? "" : "dim"}>
              <td>{row.name}</td>
              <td className="mono">{row.value}</td>
              <td className="mono">{row.weight}</td>
              <td className="mono">{row.contribution}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {costs(finding.confidence).length > 0 ? (
        <div className="hint">
          Not higher because:{" "}
          {costs(finding.confidence)
            .map((c) => `${c.name} cost ${c.cost.toFixed(2)}`)
            .join(", ")}
        </div>
      ) : null}

      {runId ? (
        chain ? (
          <ChainView chain={chain} runId={runId} />
        ) : (
          <button className="evidence-toggle" onClick={loadChain}>
            show the evidence chain
          </button>
        )
      ) : (
        <div className="dim">The evidence chain is served by a live run, not a replay.</div>
      )}
      {error ? <div className="notice error">{error}</div> : null}
    </div>
  );
}

function ChainView({ chain, runId }: { chain: FindingChain; runId: string }) {
  return (
    <div className="chain">
      <ol className="chain-steps">
        {chain.steps.map((step) => (
          <li key={step.kind}>
            <span className="badge">{step.kind}</span> {step.title}
            {step.detail ? <div className="dim">{step.detail}</div> : null}
          </li>
        ))}
      </ol>
      {chain.evidence.map((cited) => (
        <div className="chain-evidence" key={cited.locator}>
          <div>
            <span className="mono">{cited.locator}</span>{" "}
            {cited.evidence_id ? (
              <a className="mono evidence-link" href={evidenceLink(cited.evidence_id)} title="Its hash, integrity and custody">
                {cited.evidence_id}
              </a>
            ) : null}{" "}
            <span className="badge authority">{cited.authority}</span>{" "}
            <a href={graphSearchLink(runId, cited.locator)} title="This line in the knowledge graph">
              in the graph
            </a>
          </div>
          {cited.text ? <blockquote className="chain-text">{cited.text}</blockquote> : null}
          {cited.extractions.length ? (
            <div className="dim">extracted: {cited.extractions.join("; ")}</div>
          ) : null}
          {!cited.resolved ? <div className="note">{cited.note || "did not resolve"}</div> : null}
        </div>
      ))}
    </div>
  );
}
