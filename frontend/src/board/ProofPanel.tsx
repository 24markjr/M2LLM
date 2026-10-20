/**
 * The Proof tab of the evidence board (Phase U7): the verification receipt, and the same question
 * put to the plain model, side by side, both scored by the same sentence checker.
 */

import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { AnswerSide, Comparison, Receipt } from "../api/types";
import type { MissionView } from "../hooks/useMission";
import { Button, Notice, StatusBadge, StatusMark } from "../ui/components";
import { statusOf } from "../ui/status";
import { differences, receiptText, shortHash, tallyLine } from "./proof";

export function ProofPanel({ view, runId, finished }: { view: MissionView; runId?: string | undefined; finished: boolean }) {
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(false);

  // A replay carries both; a live run is asked once it has finished.
  useEffect(() => {
    if (view.receipt !== undefined || !runId || !finished) return;
    let cancelled = false;
    api
      .getReceipt(runId)
      .then((r) => !cancelled && setReceipt(r))
      .catch((exc: unknown) => !cancelled && setError(exc instanceof ApiError ? exc.message : "The receipt could not be loaded."));
    api
      .getComparison(runId)
      .then((c) => !cancelled && setComparison(c))
      .catch(() => undefined); // COMPARISON_NOT_RUN: offered below
    return () => {
      cancelled = true;
    };
  }, [runId, finished, view.receipt]);

  const shownReceipt = view.receipt ?? receipt;
  const shownComparison = view.comparison ?? comparison;

  const ask = async () => {
    if (!runId) return;
    setAsking(true);
    setError("");
    try {
      setComparison(await api.runComparison(runId));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The plain model could not be asked.");
    } finally {
      setAsking(false);
    }
  };

  if (!finished) return <p className="board-note">The receipt is issued when the run finishes.</p>;

  return (
    <div className="proof">
      {error ? <Notice tone="error">{error}</Notice> : null}

      <section aria-labelledby="receipt-title">
        <h4 id="receipt-title">Verification receipt</h4>
        {shownReceipt ? (
          <ReceiptView receipt={shownReceipt} />
        ) : (
          <p className="board-note">{view.receipt === null ? "This recording was made before receipts were issued." : "Loading the receipt."}</p>
        )}
      </section>

      <section aria-labelledby="compare-title">
        <h4 id="compare-title">Compared with the plain model</h4>
        <p className="board-note">
          The same question and files, given to the same model in one plain prompt: no plan, no verification. Both answers are
          checked sentence by sentence against every line of the files, by the same checker. No model grades either side.
        </p>
        {shownComparison ? (
          <ComparisonView comparison={shownComparison} />
        ) : runId ? (
          <Button onClick={() => void ask()} disabled={asking}>
            {asking ? "Asking the plain model…" : "Ask the plain model"}
          </Button>
        ) : (
          <p className="board-note">This recording has no comparison; it is run on a live investigation.</p>
        )}
      </section>
    </div>
  );
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function ReceiptView({ receipt: r }: { receipt: Receipt }) {
  return (
    <div className="receipt">
      <dl className="receipt-meta">
        <dt>Model</dt>
        <dd>{r.model}</dd>
        <dt>Prompts</dt>
        <dd>{Object.entries(r.prompt_versions).map(([k, v]) => `${k} v${v}`).join(", ") || "not recorded (a run from before receipts)"}</dd>
        <dt>Tasks</dt>
        <dd>
          {r.tasks_completed} of {r.tasks_planned} completed; {r.gaps_open} gap(s) open
        </dd>
        <dt>Answer</dt>
        <dd>{tallyLine(r.answer)}</dd>
      </dl>
      <table className="receipt-table">
        <caption>Files, hashed as read</caption>
        <thead>
          <tr>
            <th>File</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {r.documents.map((d) => (
            <tr key={d.name}>
              <td>{d.name}</td>
              <td className="mono" title={d.sha256}>
                {shortHash(d.sha256)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="receipt-table">
        <caption>Findings</caption>
        <thead>
          <tr>
            <th>Finding</th>
            <th>Checked</th>
            <th>Citations</th>
          </tr>
        </thead>
        <tbody>
          {r.findings.map((f) => (
            <tr key={f.finding_id}>
              <td title={f.claim}>{f.finding_id}</td>
              <td>
                <StatusBadge status={statusOf(f.verification)} />
                {f.degraded ? " degraded" : ""}
              </td>
              <td>
                {f.citations_resolved}/{f.citations} resolved
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="receipt-hash">
        Receipt hash <span className="mono" title={r.receipt_hash}>{shortHash(r.receipt_hash)}</span>
      </p>
      <div className="board-links">
        <Button size="sm" variant="ghost" onClick={() => download(`receipt-${r.run_id}.txt`, receiptText(r))}>
          Download receipt
        </Button>
        <Button size="sm" variant="ghost" onClick={() => download(`receipt-${r.run_id}.json`, JSON.stringify(r, null, 2))}>
          JSON
        </Button>
      </div>
    </div>
  );
}

function ComparisonView({ comparison: c }: { comparison: Comparison }) {
  return (
    <div className="compare">
      <ul className="compare-diff">
        {differences(c).map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <div className="compare-sides">
        <Side side={c.plain} />
        <Side side={c.jarvis} />
      </div>
      <p className="board-note">
        {c.model} · checked against {c.evidence_lines} lines · {new Date(c.generated_at).toLocaleString()}
      </p>
    </div>
  );
}

function Side({ side }: { side: AnswerSide }) {
  const sentences = side.check?.sentences ?? [];
  return (
    <div className="compare-side">
      <h5>{side.label}</h5>
      <p className="board-note">{tallyLine(side.tally)}</p>
      <p className="compare-answer">
        {sentences.length
          ? sentences.map((s, i) => (
              <span key={i}>
                <StatusMark status={statusOf(s.status)}>{s.sentence}</StatusMark>{" "}
              </span>
            ))
          : side.answer || "No answer."}
      </p>
      {side.ungrounded.length ? (
        <p className="compare-flag">In no file: {side.ungrounded.join(", ")}</p>
      ) : null}
      {side.latency_ms ? <p className="board-note">{(side.latency_ms / 1000).toFixed(1)} s</p> : null}
    </div>
  );
}
