# The investigation journal (Phase U5)

Code: `frontend/src/journal/` - `JournalPage.tsx` (`JournalPage`, `Journal`), `journal.ts` (steps,
answer, citations, closing; pure and tested), `RecordingsPage.tsx` (recordings and replay),
`journal.css`; `shell/ErrorBoundary.tsx`.

`#/mission/{id}` is the journal. The page every panel lived on before is `#/mission/{id}/details`
("All details"), until the evidence board (U6) takes its panels over.

## What it shows, top to bottom

1. **The question as asked**, its mode, case, time and state, and the files (each linked to its
   evidence item). Stop while it runs; All details, Knowledge graph and Delete when it has finished.
2. **What it is doing**, in seven plain steps - understanding the question, planning, reading the
   files, drawing findings, checking each finding against its lines, looking for what is missing,
   writing the answer - each with what happened in it so far ("1 of 2 verified", "1 gap, 0 closed,
   1 new round of work - latest: the approved end date"). Open while running, folded to one line
   ("Done in 7 steps, 1 extra round of work to close gaps") when finished. Underneath: what the mode
   added to the plan, and the planned steps in plain words, marking the ones added to close a gap.
   Built from the event stream and the task graph only (`journalSteps`).
3. **The answer**: the executive summary, each sentence marked with the status the narrative check
   gave it (Phase 37) - verified, inferred, not established, unknown - with a legend. A summary that
   was not checked sentence by sentence is shown as one passage marked unknown, and says so.
4. **Findings**: status, statement type, computed confidence, review state; the claim; numbered
   citation chips (file and line or page, linked to the evidence item; dashed when unresolved);
   "Why this confidence, review and challenge" opens the existing confidence breakdown, review and
   challenge panels.
5. **Three closing sections**, from the run's own record (`closingSections`):
   - *What I could not establish* - unresolved gaps, findings not established, the report's
     limitations with their causes;
   - *What would change this answer* - open hypotheses and the evidence that would decide them;
     inferred findings, and what would settle each;
   - *Best next evidence to get* - each live hypothesis's next evidence.
   Each says plainly when it is empty.
6. **Ask a follow-up**: a new investigation over the same files, in the same case and mode.

Deleting asks first and says what is kept; it uses `DELETE /missions/{id}` (U1c).

## Replay in place; recordings as records

`Journal` takes a `MissionView`, the shape both a live run (`useMission`) and a recording
(`useReplay`) produce, so a replay renders through exactly the same code. `#/replay/{file}` plays a
recording in the journal under a bar that says it is a replay, when it was recorded and on which
model, with play/pause, skip to the end and speed.

Insights > Recordings (`#/replay`) is now a table - question, how it ended, verified/total findings,
case, duration, when - in place of 101 unnamed buttons. Failed runs with no findings and second
copies are hidden unless shown (U1b). Delete one (a committed recording is "kept"), delete the failed
and duplicates, or delete all (typing "delete" to confirm). Short columns stay on one line
(`Column.nowrap`); table cells break a word only when it cannot fit a line of its own.

## A page that fails says so

The headless check of a replay found the whole console going blank partway through: a rendering
error unmounts the React root. `ErrorBoundary` now wraps each page inside the shell, keyed by the
route: a failing page shows "This page could not be shown", the error, and Try again, while the
sidebar and every other page keep working. The error it caught was BUG-041.

## Verified

Unit tests for steps (running, finished, never reached), sentence statuses, citations and the
closing sections. In headless Chrome against a temporary API: the Aurora demo recording replayed in
the journal mid-run (steps) and to the end (answer, four findings with citations, closing sections,
read from the DOM - a long fast-forward does not screenshot); the recordings table at 1440 px.
