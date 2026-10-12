/**
 * What the run's security logs show (Phase 52), read without a model: indicators, observed relations
 * with the lines that state them, decoded commands, per-host and per-account timelines. Other cases
 * sharing indicators appear only when the case has opted in, labelled as context - never evidence.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { CyberAnalysis } from "../api/types";
import { caseLink } from "./cases";
import { hasEvents, indicatorsByKind, relationText } from "./cyber";

export function CyberPanel({ runId, caseId }: { runId?: string | undefined; caseId?: string | undefined }) {
  const [analysis, setAnalysis] = useState<CyberAnalysis | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    if (!runId) return;
    api
      .getCyber(runId)
      .then(setAnalysis)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };
  useEffect(load, [runId]);

  if (!runId || !hasEvents(analysis) || !analysis) return error ? <div className="notice error">{error}</div> : null;

  const optIn = () => {
    if (!caseId) return;
    api
      .updateCase(caseId, { recall_similar: true })
      .then(load)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  return (
    <div className="panel">
      <h2>
        Security logs <span className="count">{analysis.events} event(s) · read without a model</span>
      </h2>
      <div className="panel-body">
        {analysis.decoded_commands.length ? (
          <>
            <div className="why-head">Decoded commands</div>
            {analysis.decoded_commands.map((c) => (
              <div className="gap-item" key={c.locator}>
                <span className="mono">{c.locator}</span> {c.host} {c.user ? `(${c.user})` : ""}
                <div className="mono">{c.script}</div>
              </div>
            ))}
          </>
        ) : null}
        <div className="why-head">Indicators</div>
        {indicatorsByKind(analysis).map(([kind, values]) => (
          <div key={kind}>
            <span className="badge">{kind}</span> <span className="mono">{values.join(", ")}</span>
          </div>
        ))}
        <div className="why-head">Observed relations</div>
        <ul>
          {analysis.relations.map((r) => (
            <li key={`${r.subject}-${r.predicate}-${r.object}`}>
              {relationText(r)} <span className="dim mono">{r.sources.join(", ")}</span>
            </li>
          ))}
        </ul>
        {(["host_timelines", "account_timelines"] as const).map((key) => (
          <div key={key}>
            <div className="why-head">{key === "host_timelines" ? "Per host" : "Per account"}</div>
            {Object.entries(analysis[key]).map(([name, items]) => (
              <details key={name}>
                <summary>
                  {name} <span className="dim">{items.length} event(s)</span>
                </summary>
                <ol className="chain-steps">
                  {items.map((item) => (
                    <li key={item.locator}>
                      <span className="mono dim">{item.time}</span> {item.summary}{" "}
                      <span className="mono dim">{item.locator}</span>
                    </li>
                  ))}
                </ol>
              </details>
            ))}
          </div>
        ))}
        <div className="why-head">Similar cases (context, never evidence)</div>
        <div className="dim">{analysis.recall}</div>
        {analysis.similar_cases.map((s) => (
          <div key={s.case_id}>
            <a href={caseLink(s.case_id)}>{s.case_id}</a> shares <span className="mono">{s.shared.join(", ")}</span>
          </div>
        ))}
        {caseId && analysis.recall.startsWith("off: the case") ? (
          <button onClick={optIn}>Recall similar cases for this case</button>
        ) : null}
        {error ? <div className="notice error">{error}</div> : null}
      </div>
    </div>
  );
}
