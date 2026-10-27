/**
 * Following an investigation up (v4 Phase 3b): answering the question a run stopped to ask, and a
 * finding's history - every recorded change, oldest first.
 */

import { useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { FindingHistory } from "../api/types";
import { Button, Notice } from "../ui/components";

/** A run that stopped to ask a question: answer it, and the investigation starts again with it. */
export function ClarifyReply({ runId, question }: { runId: string; question: string }) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await api.clarify(runId, answer.trim());
      window.location.hash = `#/mission/${next.run_id}`;
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The answer could not be sent.");
      setBusy(false);
    }
  };

  return (
    <Notice tone="warning">
      <form className="row talk-ask" onSubmit={(e) => void send(e)}>
        <span>
          It needs a clearer question before it can plan: <strong>{question}</strong>
        </span>
        <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer" maxLength={2000} />
        <Button size="sm" type="submit" disabled={busy || !answer.trim()}>
          {busy ? "Starting." : "Answer and continue"}
        </Button>
      </form>
      {error ? <div>{error}</div> : null}
    </Notice>
  );
}

/** A finding's history, loaded when opened. */
export function FindingHistoryPanel({ runId, findingId }: { runId: string; findingId: string }) {
  const [history, setHistory] = useState<FindingHistory | null>(null);
  const [open, setOpen] = useState(false);

  const toggle = () => {
    if (!open && history === null) {
      void api
        .findingHistory(runId, findingId)
        .then(setHistory)
        .catch(() => setHistory({ run_id: runId, finding_id: findingId, claim: "", entries: [] }));
    }
    setOpen(!open);
  };

  return (
    <div className="finding-history">
      <button className="link" onClick={toggle}>
        {open ? "hide history" : "history"}
      </button>
      {open && history ? (
        history.entries.length ? (
          <ol className="dim">
            {history.entries.map((e, i) => (
              <li key={i}>
                <strong>{e.kind}</strong> {e.summary}
                {e.by && e.by !== "system" ? ` - ${e.by}` : ""}
                {e.at ? ` · ${new Date(e.at).toLocaleString()}` : ""}
              </li>
            ))}
          </ol>
        ) : (
          <p className="dim">Nothing recorded beyond the finding itself.</p>
        )
      ) : null}
    </div>
  );
}
