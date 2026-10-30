/**
 * The investigation journal (Phase U5): what was asked, what the engine is doing in plain words, the
 * answer with every sentence marked by its status, the findings with their citations, review and
 * challenge, and the three closing sections. A follow-up question continues in the same case.
 *
 * Driven by a `MissionView`, so a live run and a replay render through the same code.
 */

import { useState } from "react";
import { ProgressLine } from "../components/ProgressLine";

import { api, ApiError } from "../api/client";
import type { Finding, FindingReview } from "../api/types";
import { EvidenceBoard, type BoardFocus, type BoardTab } from "../board/EvidenceBoard";
import { ChallengePanel } from "../components/ChallengePanel";
import { ConfidenceWhy } from "../components/ConfidenceWhy";
import { evidenceLabel, SCORE_NOTE } from "../components/confidence";
import { ReviewPanel } from "../components/ReviewPanel";
import { ClarifyReply, FindingHistoryPanel, RunAgain } from "./FollowUp";
import { useMission, type MissionView } from "../hooks/useMission";
import { MODE_PLANS, MODES, type Mode } from "../home/modes";
import { casesChanged } from "../shell/Sidebar";
import { Badge, Button, ConfirmDialog, Notice, StatusBadge, StatusMark, useToast } from "../ui/components";
import { IconTrash } from "../ui/icons";
import { STATUS } from "../ui/status";
import {
  answerSentences,
  citationsOf,
  closingSections,
  findingStatus,
  journalSteps,
  type Step,
} from "./journal";

const FINISHED = ["COMPLETED", "FAILED", "CANCELLED", "CLARIFICATION_NEEDED"];

export function JournalPage({ runId }: { runId: string }) {
  const live = useMission(runId);
  return <Journal view={live} runId={runId} onStop={live.cancel} />;
}

export function Journal({ view, runId, onStop }: { view: MissionView; runId?: string; onStop?: () => void }) {
  const { mission, findings, gaps, report, hypotheses, reviews, events, tasks } = view;
  const notify = useToast();
  const [showSteps, setShowSteps] = useState<boolean | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  // The evidence board (U6): a citation clicked in a finding opens its file there, marked.
  const [focus, setFocus] = useState<BoardFocus | null>(null);
  const [tab, setTab] = useState<BoardTab>("sources");
  const [wide, setWide] = useState(false);
  const cite = (document: string, findingId: string) => {
    setFocus({ document, findingId, nonce: Date.now() });
    setTab("sources");
    setWide(false);
  };

  if (!mission) {
    return view.error ? <Notice tone="error">{view.error}</Notice> : <div className="journal-loading">Opening the investigation.</div>;
  }

  const finished = FINISHED.includes(mission.status);
  const steps = journalSteps(events, tasks, finished);
  const stepsOpen = showSteps ?? !finished;
  const sentences = answerSentences(report);
  const closing = closingSections(findings, gaps, hypotheses, report);
  const mode = (mission.mode ?? "investigate") as Mode;
  const modeLabel = MODES.find((m) => m.id === mode)?.label ?? "Investigate";
  const reviewOf = (id: string): FindingReview | undefined => reviews?.find((r) => r.finding_id === id);
  const evidence = mission.evidence ?? {};

  const remove = async () => {
    setBusy(true);
    try {
      const result = await api.deleteMission(mission.run_id);
      notify(`Deleted: ${result.removed.length} place(s) cleared; custody, reviews and the audit log kept.`, "success");
      casesChanged();
      window.location.hash = mission.case_id ? `#/case/${mission.case_id}` : "#/";
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "It could not be deleted.", "error");
      setBusy(false);
      setDeleting(false);
    }
  };

  return (
    <div className={`workspace ${wide ? "board-wide" : ""}`}>
    <article className="journal">
      {/* --- the question ------------------------------------------------------------------------ */}
      <header className="journal-ask">
        <div className="journal-ask-meta">
          <Badge tone="accent">{modeLabel}</Badge>
          {mission.case_id ? <a href={`#/case/${mission.case_id}`}>{mission.case_id}</a> : <span>No case</span>}
          <span>{new Date(mission.created_at).toLocaleString()}</span>
          <RunState status={mission.status} />
        </div>
        {"original_objective" in mission && mission.original_objective ? (
          <>
            {/* Asked in an Indian language (v4 Phase 7): shown as asked, with the English it ran on. */}
            <h1 className="journal-question" lang={mission.asked_in}>
              {mission.original_objective}
            </h1>
            <p className="dim">Investigated in English as: {mission.objective}</p>
          </>
        ) : (
          <h1 className="journal-question">{mission.objective}</h1>
        )}
        {"translated_documents" in mission && mission.translated_documents?.length ? (
          <p className="dim">
            Read through a line-aligned English translation: {mission.translated_documents.join(", ")}. The originals stay the
            evidence; in the case's conversation a citation opens original and translation side by side.
          </p>
        ) : null}
        {mission.documents.length ? (
          <ul className="journal-files" aria-label="Files">
            {mission.documents.map((name) => (
              <li key={name}>
                {evidence[name] ? <a href={`#/evidence/${evidence[name]}`}>{name}</a> : name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="journal-note">No files were attached.</p>
        )}
        <div className="journal-actions">
          {!finished && onStop ? (
            <Button variant="secondary" onClick={onStop}>
              Stop
            </Button>
          ) : null}
          {runId ? (
            <>
              <a className="ui-button ghost sm" href={`#/mission/${runId}/details`}>
                All details
              </a>
              {mission.knowledge_store ? (
                <a className="ui-button ghost sm" href={`#/mission/${runId}/graph`}>
                  Knowledge graph
                </a>
              ) : null}
              {finished ? <RunAgain runId={runId} objective={mission.objective} /> : null}
              {finished ? (
                <Button variant="ghost" size="sm" icon={<IconTrash size={14} />} onClick={() => setDeleting(true)}>
                  Delete
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      </header>

      {/* --- what it is doing -------------------------------------------------------------------- */}
      <section className={`journal-steps ${stepsOpen ? "open" : ""}`}>
        <button type="button" className="journal-steps-toggle" aria-expanded={stepsOpen} onClick={() => setShowSteps(!stepsOpen)}>
          <span className={`step-dot ${finished ? "done" : "doing"}`} aria-hidden="true" />
          {finished ? stepSummary(steps, mission.replan_iterations) : currentStep(steps)}
          <span className="journal-steps-chevron" aria-hidden="true">
            {stepsOpen ? "Hide" : "Show"} how
          </span>
        </button>
        {finished ? null : <ProgressLine events={events} startedAt={mission.created_at} tasksTotal={tasks?.nodes.length ?? 0} />}
        {stepsOpen ? (
          <ol className="steps">
            {steps.map((s) => (
              <li key={s.id} className={`step ${s.state}`}>
                <span className="step-dot" aria-hidden="true" />
                <span className="step-label">{s.label}</span>
                {s.detail ? <span className="step-detail">{s.detail}</span> : null}
                <span className="ui-sr">({s.state})</span>
              </li>
            ))}
            {MODE_PLANS[mode] ? <li className="step-note">{MODE_PLANS[mode]}</li> : null}
            {tasks?.nodes.length ? (
              <li className="step-tasks">
                <details>
                  <summary>The {tasks.nodes.length} planned step(s)</summary>
                  <ul>
                    {tasks.nodes.map((t) => (
                      <li key={t.task_id} className={`task-line ${t.status.toLowerCase()}`}>
                        {t.label ?? t.description}
                        {t.inserted_by_replan ? <Badge tone="inferred">added to close a gap</Badge> : null}
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ) : null}
          </ol>
        ) : null}
      </section>

      {view.error ? <Notice tone="error">{view.error}</Notice> : null}
      {mission.status === "FAILED" ? (
        <Notice tone="error">
          The investigation stopped: {mission.error_message || mission.error_code || "an error"}. Everything it reached is shown.
        </Notice>
      ) : null}
      {mission.status === "CLARIFICATION_NEEDED" ? (
        runId ? (
          <ClarifyReply runId={runId} question={mission.clarification_question} />
        ) : (
          <Notice tone="warning">It needs a clearer question before it can plan: {mission.clarification_question}</Notice>
        )
      ) : null}

      {/* --- the answer -------------------------------------------------------------------------- */}
      <section className="journal-answer" aria-labelledby="answer-title">
        <h2 id="answer-title">Answer</h2>
        {sentences.length ? (
          <p className="answer-text">
            {sentences.map((s, i) => (
              <span key={i}>
                <StatusMark status={s.status}>{s.text}</StatusMark>{" "}
              </span>
            ))}
          </p>
        ) : finished ? (
          <p className="journal-note">No written answer: {findings.length ? "see the findings below." : "nothing in the files answered the question."}</p>
        ) : (
          <p className="journal-note">The answer is written once every finding has been checked.</p>
        )}
        {sentences.length ? <Legend /> : null}
      </section>

      {/* --- findings ---------------------------------------------------------------------------- */}
      <section className="journal-findings" aria-labelledby="findings-title">
        <h2 id="findings-title">
          Findings <span className="count">{findings.length}</span>
        </h2>
        {findings.length === 0 ? (
          <p className="journal-note">{finished ? "No finding: nothing in the files established an answer." : "None yet."}</p>
        ) : (
          findings.map((f) => <FindingCard key={f.finding_id} finding={f} evidence={evidence} review={reviewOf(f.finding_id)} runId={runId} onCite={cite} />)
        )}
      </section>

      {/* --- closing ----------------------------------------------------------------------------- */}
      {finished ? (
        <section className="journal-closing" aria-label="What is left">
          <ClosingList title="What I couldn't establish" items={closing.couldNot} empty="Everything asked was established or answered." />
          <ClosingList title="What would change this answer" items={closing.wouldChange} empty="Nothing open: every explanation the evidence could decide was decided." />
          <ClosingList title="Best next evidence to get" items={closing.next} empty="No further evidence was identified as decisive." />
        </section>
      ) : null}

      {/* --- follow-up --------------------------------------------------------------------------- */}
      {finished && runId ? <FollowUp mission={mission} mode={mode} /> : null}

      <ConfirmDialog
        open={deleting}
        title="Delete this investigation?"
        busy={busy}
        body={
          <p>
            Its answer, findings, recording and memory go. Kept: the files in the Library, their chain of custody, review
            decisions and the audit log.
          </p>
        }
        confirmLabel="Delete"
        onClose={() => setDeleting(false)}
        onConfirm={() => void remove()}
      />
    </article>
    <EvidenceBoard view={view} runId={runId} focus={focus} tab={tab} onTab={setTab} wide={wide} onWide={setWide} />
    </div>
  );
}

function FindingCard({
  finding,
  evidence,
  review,
  runId,
  onCite,
}: {
  finding: Finding;
  evidence: Record<string, string>;
  review: FindingReview | undefined;
  runId: string | undefined;
  onCite: (document: string, findingId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const status = findingStatus(finding);
  const citations = citationsOf(finding, evidence);
  return (
    <div className={`finding-card ${status}`}>
      <div className="finding-head">
        <StatusBadge status={status} />
        {finding.statement_type ? <Badge>{finding.statement_type.replaceAll("_", " ").toLowerCase()}</Badge> : null}
        <span className="finding-confidence" title={`${finding.confidence.value.toFixed(2)}. ${SCORE_NOTE}`}>
          {evidenceLabel(finding.confidence.value)}
        </span>
        {review?.state && review.state !== "PENDING" ? <Badge tone="accent">{review.state.toLowerCase()}</Badge> : null}
        {review?.required && review.state === "PENDING" ? <Badge tone="inferred">needs review</Badge> : null}
        <span className="finding-id">{finding.finding_id}</span>
      </div>
      <p className="finding-claim">{finding.claim}</p>
      <ul className="citations" aria-label="Cited lines">
        {citations.map((c, i) => (
          <li key={c.key}>
            <button
              type="button"
              className={`citation ${c.resolved ? "" : "unresolved"}`}
              title={c.resolved ? "Show the cited line on the evidence board" : "This citation did not resolve"}
              onClick={() => onCite(c.document, finding.finding_id)}
            >
              <span className="citation-n">{i + 1}</span> {c.label}
            </button>
            {c.href ? (
              <a className="citation-custody" href={c.href} title="The file's chain of custody">
                custody
              </a>
            ) : null}
          </li>
        ))}
      </ul>
      <button type="button" className="finding-more" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Why this confidence, review and challenge"}
      </button>
      {open ? (
        <div className="finding-detail">
          <ConfidenceWhy finding={finding} runId={runId} />
          {runId ? <ReviewPanel runId={runId} review={review} /> : null}
          {runId ? <ChallengePanel runId={runId} findingId={finding.finding_id} /> : null}
          {runId ? <FindingHistoryPanel runId={runId} findingId={finding.finding_id} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function ClosingList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="closing">
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="journal-note">{empty}</p>
      )}
    </div>
  );
}

function FollowUp({ mission, mode }: { mission: { run_id: string; case_id?: string; documents: string[] }; mode: Mode }) {
  const notify = useToast();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const ask = async () => {
    if (question.trim().length < 8) return;
    setBusy(true);
    try {
      const next = await api.createMission(question.trim(), mission.documents, undefined, mission.case_id || undefined, mode);
      casesChanged();
      window.location.hash = `#/mission/${next.run_id}`;
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "The follow-up could not be started.", "error");
      setBusy(false);
    }
  };
  return (
    <section className="follow-up" aria-labelledby="follow-up-title">
      <h2 id="follow-up-title">Ask a follow-up</h2>
      <div className="follow-up-box">
        <textarea
          rows={2}
          value={question}
          placeholder="Another question about the same files"
          aria-label="Follow-up question"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <Button variant="primary" busy={busy} disabled={question.trim().length < 8} onClick={() => void ask()}>
          Ask
        </Button>
      </div>
      <p className="journal-note">
        Runs as a new investigation over the same {mission.documents.length} file(s){mission.case_id ? `, in ${mission.case_id}` : ""}.
      </p>
    </section>
  );
}

function RunState({ status }: { status: string }) {
  const tone = status === "COMPLETED" ? "verified" : status === "FAILED" ? "unsupported" : status === "RUNNING" || status === "PENDING" ? "accent" : "unknown";
  const label: Record<string, string> = {
    PENDING: "Starting",
    RUNNING: "Running",
    COMPLETED: "Finished",
    FAILED: "Stopped by an error",
    CANCELLED: "Stopped",
    CLARIFICATION_NEEDED: "Needs a clearer question",
  };
  return <Badge tone={tone}>{label[status] ?? status}</Badge>;
}

function Legend() {
  return (
    <ul className="answer-legend" aria-label="What the underlines mean">
      {(["verified", "inferred", "unsupported", "unknown"] as const).map((s) => (
        <li key={s}>
          <StatusMark status={s}>{STATUS[s].label}</StatusMark>
        </li>
      ))}
    </ul>
  );
}

function currentStep(steps: Step[]): string {
  const doing = steps.find((s) => s.state === "doing");
  return doing ? `${doing.label}${doing.detail ? ` - ${doing.detail}` : ""}` : "Starting";
}

function stepSummary(steps: Step[], replans: number): string {
  const done = steps.filter((s) => s.state === "done").length;
  return `Done in ${done} step(s)${replans ? `, ${replans} extra round(s) of work to close gaps` : ""}`;
}
