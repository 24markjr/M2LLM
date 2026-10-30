/**
 * The investigation conversation on a case's page (v4 Phases 3-4). Ask about the case; the answer
 * streams in as the model writes it, and each claim gets the verifier's mark once it is checked -
 * an unmarked claim is still being checked. Citations open the cited line in one click. An answer
 * can be asked again and a message edited; what they replace is kept, shown on request.
 *
 * In any Indian language (v4 Phase 7): typed in its own script or in Roman letters, or spoken. The
 * question is read in English, where every claim is verified; the answer comes in English - the
 * master - and in the person's language, labelled as a machine translation, and can be read aloud.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { streamTalk, type TalkEvent, type TalkRequest } from "../api/stream";
import type { AnsweredClaim, DocumentLanguage, LanguageInfo, Turn, TurnTranslation } from "../api/types";
import { SourceViewer } from "../components/SourceViewer";
import { Notice, StatusBadge } from "../ui/components";
import { statusOf } from "../ui/status";
import { liveClaims, pendingQuestion, stopLabel, toolSummary, type LiveAnswer } from "./talk";
import { useUiLanguage } from "../i18n/uiLanguage";
import { talkWords, type TalkWords } from "./talkWords";

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

/** Read text aloud: Bhashini's voice when the case may use it, else the browser's own. */
async function readAloud(text: string, translation: TurnTranslation, caseId: string): Promise<void> {
  const audio = await api.speak(text, translation.language, caseId).catch(() => null);
  if (audio) {
    void new Audio(URL.createObjectURL(audio)).play();
    return;
  }
  if (!("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = translation.speech || translation.language;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function Translated({ translation, caseId, words }: { translation: TurnTranslation; caseId: string; words: TalkWords }) {
  return (
    <div className="talk-translation" lang={translation.language}>
      <div className="dim talk-label">
        {words.translationLabel} · {translation.language_name} · {translation.engine}
        {translation.fallback ? " (fallback)" : ""}{" "}
        <button className="link" onClick={() => void readAloud(translation.text, translation, caseId)}>
          {words.readAloud}
        </button>
      </div>
      <p>{translation.text}</p>
    </div>
  );
}

function AssistantTurn({
  turn,
  caseId,
  words,
  onPin,
  onRegenerate,
  onOpen,
  busy,
}: {
  turn: Turn;
  caseId: string;
  words: TalkWords;
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
      {turn.translation ? <Translated translation={turn.translation} caseId={caseId} words={words} /> : null}
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
              {words.askAgain}
            </button>
            <button className="link" onClick={onPin}>
              {turn.pinned ? words.unpin : words.pin}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function UserTurn({
  turn,
  busy,
  words,
  onEdit,
}: {
  turn: Turn;
  busy: boolean;
  words: TalkWords;
  onEdit: (text: string) => void;
}) {
  const asked = turn.original_text || turn.text;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(asked);
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
          {words.askInstead}
        </button>
        <button type="button" className="link" onClick={() => setEditing(false)}>
          {words.cancel}
        </button>
      </form>
    );
  }
  return (
    <div className={`talk-turn user${turn.superseded ? " superseded" : ""}`} lang={turn.language || undefined}>
      {asked}
      {turn.superseded ? null : (
        <button className="link talk-edit" onClick={() => setEditing(true)} disabled={busy}>
          {words.edit}
        </button>
      )}
      {turn.transliterated ? (
        <div className="dim talk-english">
          {words.typedAs}: {turn.transliterated} ({turn.transliteration_engine})
        </div>
      ) : null}
      {turn.original_text ? (
        <div className="dim talk-english" lang="en">
          {words.readInEnglish}: {turn.text} ({turn.translation_engine})
        </div>
      ) : null}
      {turn.language_note ? <div className="dim talk-english">{turn.language_note}</div> : null}
    </div>
  );
}

/** Records a spoken question with the browser's microphone, then has it written down. */
function useRecorder(language: string, onText: (text: string) => void, onError: (message: string) => void) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const recorder = useRef<MediaRecorder | null>(null);

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onError("unavailable");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onError("unavailable");
      return;
    }
    const chunks: Blob[] = [];
    const media = new MediaRecorder(stream);
    media.ondataavailable = (e) => chunks.push(e.data);
    media.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setState("transcribing");
      api
        .transcribe(new Blob(chunks, { type: media.mimeType || "audio/webm" }), language)
        .then((t) => onText(t.text))
        .catch((exc: unknown) => onError(exc instanceof ApiError ? exc.message : "The recording could not be read."))
        .finally(() => setState("idle"));
    };
    recorder.current = media;
    media.start();
    setState("recording");
  };
  const stop = () => recorder.current?.stop();
  return { state, start, stop };
}

export function ConversationPanel({ caseId, closed }: { caseId: string; closed: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [live, setLive] = useState<LiveAnswer | null>(null);
  const [earlier, setEarlier] = useState(false);
  const [sources, setSources] = useState<Record<string, string> | null>(null);
  const [originals, setOriginals] = useState<Record<string, DocumentLanguage>>({});
  const [opened, setOpened] = useState("");
  const [starters, setStarters] = useState<string[]>([]);
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  // The console's language (the top bar, Settings, or this panel): one choice everywhere.
  const [language, setLanguage] = useUiLanguage();
  const words = talkWords(language);

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
    void api
      .languages()
      .then((c) => setLanguages(c.languages.filter((l) => l.code !== "en")))
      .catch(() => setLanguages([]));
  }, [caseId]);

  const open = useCallback(
    (locator: string) => {
      setOpened(locator);
      if (sources === null) {
        void api
          .caseSources(caseId)
          .then(setSources)
          .catch(() => setSources({}));
        void api
          .caseOriginals(caseId)
          .then(setOriginals)
          .catch(() => setOriginals({}));
      }
    },
    [caseId, sources],
  );

  const recorder = useRecorder(
    language,
    (spoken) => setText(spoken),
    (message) => setError(message === "unavailable" ? words.micUnavailable : message),
  );

  const choose = (code: string) => setLanguage(code);

  const run = async (body: TalkRequest, question: string) => {
    setBusy(true);
    setError("");
    setLive({ question, activity: "Starting", claims: [] });
    try {
      const thread = await streamTalk(caseId, { ...body, language }, (event: TalkEvent) =>
        setLive((now) => liveClaims(now, event)),
      );
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
    <div className="panel" lang={language || "en"}>
      <h2>
        {words.title}{" "}
        <span className="count">
          {turns.filter((t) => t.role === "user" && !t.superseded).length} {words.questions}
        </span>
      </h2>
      <div className="panel-body talk">
        <label className="talk-language dim">
          {words.language}
          <select value={language} onChange={(e) => choose(e.target.value)} disabled={busy}>
            <option value="">{words.detect}</option>
            {languages.map((l) => (
              <option key={l.code} value={l.code}>
                {l.native} ({l.name})
              </option>
            ))}
          </select>
        </label>
        {turns.length || live ? null : (
          <p className="dim">
            {words.intro}
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
              words={words}
              onEdit={(edited) => void run({ edit: turn.turn_id, text: edited }, edited)}
            />
          ) : (
            <AssistantTurn
              key={turn.turn_id}
              turn={turn}
              caseId={caseId}
              words={words}
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
        {recorder.state !== "idle" ? (
          <div className={`dim${recorder.state === "recording" ? " talk-recording" : ""}`} aria-live="polite">
            {recorder.state === "recording" ? words.listening : words.transcribing}
          </div>
        ) : null}
        <form className="row talk-ask" onSubmit={send}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={question ? `${words.answerPrefix}: ${question}` : words.placeholder}
            disabled={busy || closed}
            maxLength={4000}
          />
          <button
            type="button"
            className="ghost"
            onClick={() => void (recorder.state === "recording" ? recorder.stop() : recorder.start())}
            disabled={busy || closed || recorder.state === "transcribing"}
            aria-pressed={recorder.state === "recording"}
          >
            {recorder.state === "recording" ? words.stop : words.speak}
          </button>
          <button type="submit" disabled={busy || closed || !text.trim()}>
            {busy ? words.working : words.ask}
          </button>
        </form>
      </div>
      {opened && sources ? (
        <SourceViewer texts={sources} originals={originals} locator={opened} onClose={() => setOpened("")} />
      ) : null}
    </div>
  );
}
