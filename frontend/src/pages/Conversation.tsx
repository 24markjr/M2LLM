/**
 * The investigation conversation on a case's page (v4 Phases 3-4). Ask about the case; the answer
 * streams in as the model writes it, and each claim gets the verifier's mark once it is checked -
 * an unmarked claim is still being checked. Citations open the cited line in one click. An answer
 * can be asked again and a message edited; what they replace is kept, shown on request.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { streamTalk, type TalkEvent, type TalkRequest } from "../api/stream";
import type { AnsweredClaim, Turn } from "../api/types";
import { SourceViewer } from "../components/SourceViewer";
import { Notice, StatusBadge } from "../ui/components";
import { statusOf } from "../ui/status";
import { liveClaims, pendingQuestion, stopLabel, toolSummary, type LiveAnswer } from "./talk";

function Citations({ claim, onOpen }: { claim: AnsweredClaim; onOpen: (locator: string) => void }) {
  if (!claim.citations.length) return <span className="dim">(cites nothing - not verified)</span>;
  return (
    <span className="dim">
      (
      {claim.citations.map((c, i) => (
        <span key={c}>
          {i ? ", " : ""}
          <button className="link mono" onClick={() => onOpen(c)} title="Open the cited line">
            {c}
          </button>
        </span>
      ))}
      )
    </span>
  );
}

function ClaimLine({ claim, onOpen }: { claim: AnsweredClaim; onOpen: (locator: string) => void }) {
  return (
    <li>
      {claim.status ? (
        <StatusBadge status={statusOf(claim.status === "UNVERIFIED" ? "" : claim.status)} />
      ) : (
        <span className="dim talk-checking">checking</span>
      )}{" "}
      {claim.text} {claim.status ? <Citations claim={claim} onOpen={onOpen} /> : null}
      {claim.issues.length ? <div className="dim talk-issue">{claim.issues[0]}</div> : null}
    </li>
  );
}

function AssistantTurn({
  turn,
  onPin,
  onRegenerate,
  onOpen,
  busy,
}: {
  turn: Turn;
  onPin: () => void;
  onRegenerate: () => void;
  onOpen: (locator: string) => void;
  busy: boolean;
}) {
  const note = stopLabel(turn.stop_reason);
  return (
    <div className={`talk-turn assistant${turn.pinned ? " pinned" : ""}${turn.superseded ? " superseded" : ""}`}>
      {turn.superseded ? <div className="dim talk-meta">earlier answer</div> : null}
      {turn.claims.length ? (
        <ul className="talk-claims">
          {turn.claims.map((claim, i) => (
            <ClaimLine key={i} claim={claim} onOpen={onOpen} />
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
        {turn.superseded ? null : (
          <>
            <button className="link" onClick={onRegenerate} disabled={busy}>
              ask again
            </button>
            <button className="link" onClick={onPin}>
              {turn.pinned ? "unpin" : "pin"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function UserTurn({ turn, busy, onEdit }: { turn: Turn; busy: boolean; onEdit: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(turn.text);
  if (editing) {
    return (
      <form
        className="talk-turn user row"
        onSubmit={(e) => {
          e.preventDefault();
          setEditing(false);
          onEdit(text.trim());
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} autoFocus />
        <button type="submit" disabled={!text.trim() || busy}>
          Ask this instead
        </button>
        <button type="button" className="link" onClick={() => setEditing(false)}>
          cancel
        </button>
      </form>
    );
  }
  return (
    <div className={`talk-turn user${turn.superseded ? " superseded" : ""}`}>
      {turn.text}
      {turn.superseded ? null : (
        <button className="link talk-edit" onClick={() => setEditing(true)} disabled={busy}>
          edit
        </button>
      )}
    </div>
  );
}

export function ConversationPanel({ caseId, closed }: { caseId: string; closed: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [live, setLive] = useState<LiveAnswer | null>(null);
  const [earlier, setEarlier] = useState(false);
  const [sources, setSources] = useState<Record<string, string> | null>(null);
  const [opened, setOpened] = useState("");
  const [starters, setStarters] = useState<string[]>([]);

  useEffect(() => {
    api
      .conversation(caseId)
      .then((thread) => setTurns(thread.turns))
      .catch((exc: unknown) => setError(exc instanceof ApiError ? exc.message : "Could not load the conversation."));
    // The organisation's domain pack suggests first questions (v4 Phase 10).
    void api
      .packs()
      .then((p) => setStarters(p.packs.find((x) => x.id === p.current)?.starter_questions ?? []))
      .catch(() => setStarters([]));
  }, [caseId]);

  const open = useCallback(
    (locator: string) => {
      setOpened(locator);
      if (sources === null) {
        void api
          .caseSources(caseId)
          .then(setSources)
          .catch(() => setSources({}));
      }
    },
    [caseId, sources],
  );

  const run = async (body: TalkRequest, question: string) => {
    setBusy(true);
    setError("");
    setLive({ question, activity: "Starting", claims: [] });
    try {
      const thread = await streamTalk(caseId, body, (event: TalkEvent) => setLive((now) => liveClaims(now, event)));
      setTurns(thread.turns);
      setText("");
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The question could not be answered.");
    } finally {
      setBusy(false);
      setLive(null);
    }
  };

  const send = (e: FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (message) void run({ text: message }, message);
  };

  const pin = async (turn: Turn) => {
    setTurns((await api.pinTurn(caseId, turn.turn_id, !turn.pinned)).turns);
  };

  const question = pendingQuestion(turns.filter((t) => !t.superseded));
  const hidden = turns.filter((t) => t.superseded).length;
  const shown = earlier ? turns : turns.filter((t) => !t.superseded);
  return (
    <div className="panel">
      <h2>
        Ask about this case{" "}
        <span className="count">{turns.filter((t) => t.role === "user" && !t.superseded).length} question(s)</span>
      </h2>
      <div className="panel-body talk">
        {turns.length || live ? null : (
          <p className="dim">
            Ask about the case's documents and findings. Every claim in an answer is checked against the lines it cites
            before it is marked. Name a finding to re-check it: "recheck F-002".
            {starters.length ? (
              <span className="talk-starters">
                {starters.map((q) => (
                  <button key={q} className="link" onClick={() => setText(q)}>
                    {q}
                  </button>
                ))}
              </span>
            ) : null}
          </p>
        )}
        {hidden ? (
          <button className="link talk-earlier" onClick={() => setEarlier(!earlier)}>
            {earlier ? "hide" : "show"} {hidden} earlier version(s)
          </button>
        ) : null}
        {shown.map((turn) =>
          turn.role === "user" ? (
            <UserTurn
              key={turn.turn_id}
              turn={turn}
              busy={busy}
              onEdit={(edited) => void run({ edit: turn.turn_id, text: edited }, edited)}
            />
          ) : (
            <AssistantTurn
              key={turn.turn_id}
              turn={turn}
              busy={busy}
              onOpen={open}
              onPin={() => void pin(turn)}
              onRegenerate={() => void run({ regenerate: turn.turn_id }, "")}
            />
          ),
        )}
        {live ? (
          <>
            {live.question ? <div className="talk-turn user">{live.question}</div> : null}
            <div className="talk-turn assistant" aria-live="polite">
              {live.claims.length ? (
                <ul className="talk-claims">
                  {live.claims.map((claim, i) => (
                    <ClaimLine key={i} claim={claim} onOpen={open} />
                  ))}
                </ul>
              ) : null}
              <div className="dim talk-meta">{live.activity}...</div>
            </div>
          </>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
        <form className="row talk-ask" onSubmit={send}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={question ? `Answer: ${question}` : "Ask about this case"}
            disabled={busy || closed}
            maxLength={4000}
          />
          <button type="submit" disabled={busy || closed || !text.trim()}>
            {busy ? "Working." : "Ask"}
          </button>
        </form>
      </div>
      {opened && sources ? <SourceViewer texts={sources} locator={opened} onClose={() => setOpened("")} /> : null}
    </div>
  );
}
