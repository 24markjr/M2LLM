# JARVIS v3 — the redesign, then the rest (Phases U0–U11, B1–B10)

**Status:** agreed 2026-10-13. U1 and U2 in progress.

**Why this plan exists.** A walk through the console on 2026-10-12 found engineering screens rather
than a product: the same function under different names (Cases and Missions; Knowledge "analyze" and
New mission; Documents, Evidence and "earlier uploads"; Replay and a mission's history), a run
history of 101 unnamed recordings most of which were empty, nothing that could be deleted, an
evaluation table running off the page, and an audit log showing nothing. The user asked for an
interface in the family of ChatGPT, Claude and Gemini, but distinct, useful to any domain, and for
the UI to be rebuilt before anything else.

**Order (the user's decision):** all of Part A, then Part B. One commit per phase and per sub-phase;
a pause after each phase. **The default theme is light**; dark is a choice in Settings.

## The design idea: evidence-first, not chat-first

- **The home asks "What do you need to find out?"**, with files dropped in first and a "Needs your
  attention" strip (findings awaiting review, open gaps, finished runs).
- **Answers with receipts**: every sentence marked verified / inferred / not established; a hover
  shows its source line, a click opens it; every answer ends with *What I couldn't establish*,
  *What would change this answer*, *Best next evidence*.
- **A three-pane workspace**: cases (left), the investigation journal (centre), the evidence board
  (right: sources, viewer, timeline, graph, hypotheses, attack path, report).
- **Domain packs** (General, Investigation, Healthcare, Legal, Finance/Audit, Cyber; more later):
  starter questions, entity types, report template, severity rules, default sensitivity. The engine
  is the same. Healthcare is record review and decision support, never diagnosis.

## Part A — the interface

| Phase | What |
|---|---|
| U0 | Close Phase 54: docs and README figures (optional) |
| **U1** | Back end for the new UI: missions survive a restart and appear in their case; run records with title, question, date, status, duration, findings, empty/failed runs hidden, duplicates removed; delete one investigation, a case, all history, one or all recordings, each audited; rename, pin and search cases; the audit page fix |
| **U2** | Design system: colour, type and spacing tokens; **light default**, dark in Settings; buttons, inputs, cards, tables, tabs, dialogs, toasts, badges, the status underline; no horizontal scrolling; phone widths |
| U3 | App shell: sidebar (new investigation, Ctrl+K search, pinned, cases by date, Library, Insights, Settings, user), top bar; old pages merged and redirected |
| U4 | Home and composer: drop zone, domain pack picker and starters, modes (Ask, Investigate, Compare, Timeline, Security logs), case, sensitivity, depth; "Needs your attention" |
| U5 | Investigation journal: live steps in plain words, stop; answer with status underlines, finding cards, review and challenge, the three closing sections; follow-ups; replay in place |
| U6 | Evidence board: sources, viewer that highlights the cited line, timeline, graph, hypotheses, attack path, report and export; the user's "investigation pin board" idea for connections |
| U7 | Proof: the verification receipt on every report; compare with the plain model, side by side |
| U8 | Library: one table of every file, filters, custody drawer, folders |
| U9 | Insights: quality cards, trend chart split by configuration, categories, memory search, recordings |
| U10 | Settings: theme, domain defaults, model and offline status, activity (audit), retention, delete-all |
| U11 | Polish: shortcuts, accessibility, empty/error/loading states, first-run tour, demo script |

## Part B — after the interface

| Phase | What |
|---|---|
| B1 | Benchmark against the plain model and frontier models, scored against known answers (FActScore and ALCE methods) |
| B2 | Multimodal evaluation: audio, video, scan and photo against text; held-out scenarios by teammates |
| B3 | Better reading: docling, pyannote speakers, native `.evtx` |
| B4 | Independent checks: AlignScore; a second local reviewer (llm-council pattern) |
| B5 | Sigma rules for ATT&CK coverage |
| B6 | Enterprise controls (the old Phase 55, drafted): accounts, roles, routing, air-gap, encryption, share links |
| B7 | Domain packs in full; masking personal details |
| B8 | Held-out tuning (autoresearch pattern), after B2 |
| B9 | Watch folders, voice questions, languages |
| B10 | Academic deliverables; a license file |

---

## As built

Each phase records here what was actually built and how it differs from the line above.

### U1 - as built

- **U1a** (investigations survive a restart): run archives in `.agent/runs/`, restored on the
  registry's first use; BUG-040 fixed. See `architecture/run-history.md`.
- **U1b** (recordings as records): findings, case and a hidden reason per recording; delete one,
  hidden or all with `confirm=delete`; committed recordings kept.
- **U1c** (deletion): investigations, all investigations and cases, each removed everywhere it is
  held and audited; custody, reviews and the audit log kept by design.
- **U1d** (rename, pin, search): `Case.pinned` with migration `au1c0a5e0001`; `GET /cases?q=`.
