/**
 * The investigation conversation on a case's page (v4 Phase 3). Ask about the case; every claim of
 * an answer arrives with the verifier's mark and the lines it cites. "Recheck F-002" re-verifies a
 * finding and shows before and after.
 */

import { useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { Turn } from "../api/types";
import { Notice, StatusBadge } from "../ui/components";
import { statusOf } from "../ui/status";
import { pendingQuestion, stopLabel, toolSummary } from "./talk";

function AssistantTurn({ turn, onPin }: { turn: Turn; onPin: () => void }) {
  const note = stopLabel(turn.stop_reason);
  return (
    <div className={`talk-turn assistant${turn.pinned ? " pinned" : ""}`}>
      {turn.claims.length ? (
        <ul className="talk-claims">
          {turn.claims.map((claim, i) => (
            <li key={i}>
              <StatusBadge status={statusOf(claim.status === "UNVERIFIED" ? "" : claim.status)} />{" "}
              {claim.text}{" "}
              {claim.citations.length ? (
                <span className="mono dim">({claim.citations.join(", ")})</span>
              ) : (
                <span className="dim">(cites nothing - not verified)</span>
              )}
              {claim.issues.length ? <div className="dim talk-issue">{claim.issues[0]}</div> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className={turn.question ? "talk-question" : ""}>{turn.text}</p>
      )}
      {turn.rechecks.length ? (
        <table className="metrics talk-rechecks">
          <thead>
            <tr>
              <th>Finding</th>
              <th>Before</th>
              <th>After</th>
            </tr>
          </thead>
          <tbody>
            {turn.rechecks.map((r) => (
              <tr key={`${r.run_id}/${r.finding_id}`}>
                <td title={r.claim}>{r.finding_id}</td>
                <td>{r.before.toLowerCase()}</td>
                <td>
                  <strong>{r.after.toLowerCase()}</strong>
                  {r.changed ? "" : " (unchanged)"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <div className="talk-meta dim">
        {toolSummary(turn.steps)}
        {note ? ` · ${note}` : ""}
        <button className="link" onClick={onPin}>
          {turn.pinned ? "unpin" : "pin"}
        </button>
      </div>
    </div>
  );
}

export function ConversationPanel({ caseId, closed }: { caseId: string; closed: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .conversation(caseId)
      .then((thread) => setTurns(thread.turns))
      .catch((exc: unknown) => setError(exc instanceof ApiError ? exc.message : "Could not load the conversation."));
  }, [caseId]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (!message) return;
    setBusy(true);
    setError("");
    try {
      setTurns((await api.ask(caseId, message)).turns);
      setText("");
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The question could not be answered.");
    } finally {
      setBusy(false);
    }
  };

  const pin = async (turn: Turn) => {
    setTurns((await api.pinTurn(caseId, turn.turn_id, !turn.pinned)).turns);
  };

  const question = pendingQuestion(turns);
  return (
    <div className="panel">
      <h2>
        Ask about this case <span className="count">{turns.filter((t) => t.role === "user").length} question(s)</span>
      </h2>
      <div className="panel-body talk">
        {turns.length ? null : (
          <p className="dim">
            Ask about the case's documents and findings. Every claim in an answer is checked against the lines it cites
            before you see it. Name a finding to re-check it: "recheck F-002".
          </p>
        )}
        {turns.map((turn) =>
          turn.role === "user" ? (
            <div key={turn.turn_id} className="talk-turn user">
              {turn.text}
            </div>
          ) : (
            <AssistantTurn key={turn.turn_id} turn={turn} onPin={() => void pin(turn)} />
          ),
        )}
        {error ? <Notice tone="error">{error}</Notice> : null}
        <form className="row talk-ask" onSubmit={(e) => void send(e)}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={question ? `Answer: ${question}` : "Ask about this case"}
            disabled={busy || closed}
            maxLength={4000}
          />
          <button type="submit" disabled={busy || closed || !text.trim()}>
            {busy ? "Checking." : "Ask"}
          </button>
        </form>
        {busy ? <p className="dim">Looking through the case and checking each claim - this can take a minute.</p> : null}
      </div>
    </div>
  );
}
