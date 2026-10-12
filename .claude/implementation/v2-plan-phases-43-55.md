# JARVIS v2 — implementation plan, Phases 43–55

**Status:** Phases 43-52 done (2026-10-07 to 2026-10-12); Phases 53-55 to do.

**Why this plan exists.** A product review of the demo (2026-10-06) judged JARVIS a strong
investigation engine but not yet an investigation *platform*: no cases, no evidence custody, no
human review, no professional report, no cyber model. This plan turns that review into phases,
keeping what JARVIS already has and the rules it already keeps.

## What the review got right, and what it missed

The review described the teammates' standalone prototypes in places. Several of its gaps are already
closed, and the plan builds on them:

| Review says | Actual state | So the plan… |
|---|---|---|
| Security is not integrated | Every document scanned at load; untrusted text wrapped in every prompt; the injection scenario in CI's baseline | Only surfaces it in the UI and audit log |
| Confidence is "the LLM says 0.85" | `Confidence.compute()` derives it from recorded factors; a bare number cannot be constructed (invariant test) | Exposes and extends the factors; measures why many findings sit at 0.85 before changing anything |
| Everything is FACT | `FindingClassification` is recomputed from what resolved | Extends it to statement types |
| No evidence chain | Finding → evidence trail in the 3D graph; every citation resolves to a line | Builds "Why did I say this?" on it |
| Replanning is just a metric | Inserted tasks badged; gaps are events | Adds the plan diff and its reason |

**Changed from the review, to keep the project's invariants:** hypotheses are ranked by computed
support, not given a model-asserted probability; recalling earlier cases into a run is opt-in,
labelled as context, never cited as evidence (invariant 9 holds by default).

**The review's "do not" list is adopted:** no chatbot for its own sake, no generic insight cards, no
ungrounded graphs, no fake agent animation, no unexplained confidence scores, no "100% accuracy"
claims, no pretend tool calls, no pre-scripted cyber findings.

## Decisions (recommended options, recorded 2026-10-06; to be confirmed before each phase)

| # | Decision | Recommendation |
|---|---|---|
| D13 | Cyber data formats | JSON/CSV event logs, Sysmon/Windows exports as XML/JSON, syslog; native `.evtx` later; synthetic incident fixtures |
| D14 | MITRE ATT&CK source | The official STIX bundle, vendored offline, pinned to a version |
| D15 | Authentication | Local accounts (argon2 hashes, sessions) first; OIDC later behind the same seam |
| D16 | Cloud models | Supported by the router; a sensitive or air-gapped case can never route to one (enforced, tested) |
| D17 | Report export | One structured JSON report; Markdown → PDF and DOCX renderers from it (PDF library chosen in Phase 51) |
| D18 | Source authority | Tiers in YAML, set per evidence item at intake, analyst-overridable and logged; recorded as a confidence factor; never silently resolves a conflict |
| D19 | Memory recall into runs | Opt-in per case; shown as context only; never citable |

## Rules every phase keeps

Built end to end (backend, API, UI, tests, docs) and linked to the other screens; fast checks
(pytest, mypy, ruff, Vitest, tsc, build) plus at most one live measurement when the phase needs one;
documented (plan as-built, changelog, development log, bug log, an ADR where a decision is made); one
commit, then report and pause.

---

## Track A — Evidence foundation (P0)

### Phase 43 — Evidence Locker and chain of custody (M) — **DONE** 2026-10-07

- `EvidenceItem` (`EV-000001`, SHA-256, original name, kind, parser, bytes, collected at/by, source
  description, classification, integrity, case) and `CustodyEvent` (ACQUIRED, HASHED, STORED, PARSED,
  UNDERSTOOD, INDEXED, ANALYSED, CITED, REPORTED, VERIFIED, INTEGRITY_FAILED, METADATA_CHANGED; actor,
  time, details). Tables `evidence_items`, `custody_events`; a Postgres trigger makes custody
  append-only.
- Content-addressed, write-once storage (`.agent/evidence/<sha[:2]>/<sha>`); re-hash on read; a
  mismatch excludes the item from new runs and flags findings that cite it.
- Custody written by upload (acquired → indexed), missions (analysed) and findings (cited). Existing
  uploads imported with an "imported, earlier history unknown" event.
- API: list, detail, custody, verify, findings, download, metadata patch.
- UI: Evidence Locker page; evidence detail (custody timeline, preview, citing findings, re-verify);
  links from every citation, the Documents page and the New Mission picker.
- Tests: trigger immutability; tampering detected and excluded; the custody sequence; only the store
  writes to the evidence folder. Docs: `evidence-locker.md`, ADR-014.
- **Acceptance:** finding → evidence → full custody → re-verified hash, in two clicks.

**As built (Phase 43):** as planned, plus PARSE_FAILED and IMPORTED actions, `by-name` lookup,
other versions on an item's page, and `MissionDetail.evidence` (the exact item each document name
read) and `excluded_documents`. Changed from the plan: integrity is checked against the item last
acquired under a name (tampering fails; a changed fixture is a new version). Details:
`architecture/evidence-locker.md`, ADR-014.

### Phase 44 — Cases and the professional hierarchy (M–L) — **DONE** 2026-10-07

- `Case` (`CASE-2026-00001`, title, severity, status, owner, opened/closed, mode); `case_id` on runs
  and evidence; existing work moved into `CASE-LEGACY`; counters computed, never stored.
- Plain-language step labels (deterministic, a test fails if a task type has none).
- UI: case list as home; case page (Investigations, Evidence, Findings, Graph, Memory, Reports,
  Audit); New Investigation inside a case; a **Professional view** of a run by default (plain steps,
  current conclusion) with the technical trace under Advanced.
- **Acceptance:** a newcomer follows a run without seeing a task ID; an engineer still reaches all of it.

**As built (Phase 44):** as planned, with two changes. Existing missions were not moved into a
`CASE-LEGACY` case: they stay outside any case, listed at `#/missions`, which needed no migration of
in-memory runs. Investigations are recorded per case with their outcome (`case_investigations`), so a
case survives a restart. Details: `architecture/cases.md`.

### Phase 45 — Statement types and source authority (M) — **DONE** 2026-10-11

- Types OBSERVATION, SOURCE_CLAIM, FACT, INFERENCE, HYPOTHESIS, CONTRADICTION, RISK, RECOMMENDATION,
  UNKNOWN, assigned by deterministic rules (one source → SOURCE_CLAIM; two independent agreeing → FACT;
  disagreement → CONTRADICTION); the model proposes, the stricter type wins.
- Authority tiers in `.agent/config/authority.yaml`; set at intake, overridable, logged; reported on
  both sides of a conflict, never resolving it.
- Scenarios: a draft email against an approved statement (must stay a contradiction, with the
  authority note); two agreeing sources (FACT).
- **Acceptance:** no single-source FACT; every contradiction names both sides' authority.

**As built (Phase 45):** as planned, with three choices. The statement type is a second field beside
`FindingClassification`, which still caps confidence (ADR-015). A FACT is two documents with the claim
supported *or verified* - measured: a verified two-document agreement was not decomposed into
elements and would otherwise have read INFERENCE. The corroboration scenario requires the date, not
the FACT type: the model cited both documents in one finding on one run of two, and the guarantee the
rules make on every run is the downgrade (no single-source FACT, enforced by the schema). Details:
`architecture/statements-and-authority.md`.

## Track B — Trustworthy reasoning (P0/P1)

### Phase 46 — Confidence decomposition, "Why?" and the evidence chain (M) — **DONE** 2026-10-11

- First measure the confidence distribution in committed baselines and why it saturates.
- Factors, each stored with value and reason: evidence strength, independence, agreement, authority,
  contradiction penalty, verification outcome, temporal consistency, entity resolution; weights in
  YAML; still no bare number.
- "Why?": a deterministic explanation from factors and events, including why it is not higher.
- Evidence chain view: finding → claim → evidence item → document/page/line highlighted → extraction
  → reasoning → both verifiers' verdicts → conclusion, linked to the trail, Locker and custody.
- **Acceptance:** "why 0.73?" answered on screen by numbers that add up.

**As built (Phase 46):** measured first - 22 of 26 recorded findings at exactly 0.85, and rejected
findings kept 0.85. Factors as planned except two: *agreement* is folded into independence (it was
the one-document 0.85), and *entity resolution* is left out (nothing resolves entities yet; a fixed
factor would be decoration). Added: evidence strength from line vs page citations, verdict caps for
rejected findings, and the final-pass raise of verified multi-document findings to FACT - each found
by re-scoring the recorded findings offline. Applied after the replanning loop, so the baseline is
unchanged. Details: `architecture/confidence.md`.

### Phase 47 — Hypotheses, knowledge gaps, next best evidence (L) — **DONE** 2026-10-11

- Two to four competing explanations proposed by the model, tested for and against, ranked by
  computed support; open hypotheses can add tasks through the replanning loop (existing ceilings).
- Gaps in plain language; next best evidence as a search task or a request to the analyst.
- Scenarios whose answer is "undetermined": at least two hypotheses must stay open; metric
  `premature_conclusion_rate`. Latency budget: at most two model calls more per run.

**As built (Phase 47):** as planned, with one change. Open hypotheses do not add tasks to the
replanning loop: their next best evidence is a deterministic search of the attached documents (leads,
not findings) or an analyst request, and the console opens a new investigation of the leads in the
same case. Re-entering the loop would let an explanation's own search produce the findings that
then support it. Runs only for explanation questions, so other questions cost nothing. One
undetermined scenario (`lyra_outage_undetermined`), measured once: four open, none concluded.
Details: `architecture/hypotheses.md`.

### Phase 48 — Challenge JARVIS (M) — **DONE** 2026-10-11

- Counter-analysis on demand (and optionally before a report for HIGH/CRITICAL findings): search for
  counter-evidence, verify the negated claim, check authority and dates, recompute confidence; show
  before and after.
- Benchmark of planted false and true findings: `challenge_catch_rate`, `challenge_false_alarm_rate`.

**As built (Phase 48):** on demand, deterministic counter-evidence plus the configured verifier on
the counter lines; authority decides how far a challenge may move the number (overturn only from a
stronger source). The finding is never changed - the challenge sits beside it. The benchmark is
model-free and re-run in CI: catch 0.833, false alarms 0.000, one documented miss (a wrong name).
The automatic challenge before a report for HIGH/CRITICAL findings waits for severity (Phase 51).
Details: `architecture/challenge.md`.

### Phase 49 — Visible adaptive planning (M) — **DONE** 2026-10-11

- `Task.rationale` (the operation, gap or hypothesis behind it) and `Task.workstream`; revision
  snapshots before and after.
- Plan tree (objective → workstreams → tasks: why, input, action, output, dependencies, status) and a
  "JARVIS changed its plan" diff with the reason. Invariant: every task has a rationale.

**As built (Phase 49):** as planned. Rationale is assigned by rules from the task's origin, not
asked of the planner model - so no prompt changed and the baseline stands; the "hypothesis" origin
in the plan does not arise, because open hypotheses add no tasks (Phase 47). Details:
`architecture/plan-tree.md`.

## Track C — Professional result (P0)

### Phase 50 — Human review and audit log (M) — **DONE** 2026-10-11

- Review states PENDING / APPROVED / REJECTED / MODIFIED with reviewer, time and reason; rules for
  review-required (severity, unresolved contradiction, described-only, ATT&CK); a rejection can
  trigger a replan.
- Append-only audit log of every human and system action; every write endpoint audited (tested).
- Memory: only approved findings (or verified where no review is required) become facts.

**As built (Phase 50):** as planned. "A rejection can trigger a replan" is a follow-up
investigation (same question, documents and case, told what was rejected and why) rather than
re-entering the finished run's loop. Every write is audited by middleware, tested route by route
from the OpenAPI schema. The ATT&CK rule is in place and fires once Phase 53 maps techniques.
Details: `architecture/review-and-audit.md`, ADR-016.

### Phase 51 — The investigation report (M–L) — **DONE** 2026-10-11

- One structured report: header and hash; risk and executive summary from approved/verified findings
  only, every sentence grounded; findings, evidence (IDs, hashes, authority, integrity), timeline,
  path, contradictions, hypotheses, unknowns and next evidence, recommendations, limitations, full
  trace.
- Severity by declared rules. A currency and unit check (Phase 41's known issue, `UNIT_MISMATCH`).
- PDF, DOCX and JSON from one object; export written to custody and audit.

**As built (Phase 51):** as planned, plus Markdown, and Phase 48's deferred step (HIGH/CRITICAL
findings challenged before a report, deterministically). The executive summary is the established
findings' claims with citations rather than new prose - grounded by construction; synthesis's
narrative is carried with its grounding verdicts. The PDF writer is in-house (ADR-017). The content
hash covers the content, not the generation time, so the page and a download match. Details:
`architecture/investigation-report.md`.

## Track D — Cyber investigation mode (P1)

### Phase 52 — Cyber data, entities, incident timeline (L) — **DONE** 2026-10-12

- Parsers for event logs (D13), one citable event per line; cyber entities and relationships;
  deterministic IOC extraction (defanged forms included); per-host and per-account timelines.
- Case mode CYBER; opt-in recall of similar cases as context (D19), excluded from evidence by test.
- Fixtures: encoded PowerShell, lateral movement, benign admin activity (negative case).

**As built (Phase 52):** as planned. Recall is computed on demand from other CYBER cases' stored
evidence (no index table) and kept out of missions structurally. The live check found that the
model could not report what the analysis knew, so missions now receive the decoded commands and
relations through the knowledge tool, and the verifier sees a decoding beside its line; it also found
BUG-037 (ISO timestamps carried no date). Details: `architecture/cyber.md`.

### Phase 53 — MITRE ATT&CK mapping and attack paths (L)

- Vendored ATT&CK (D14); rule-based technique mapping in YAML, model suggestions labelled; every
  mapping lists indicators and evidence and needs analyst validation.
- Attack path with OBSERVED and INFERRED edges, named as such; shown in the 3D explorer.
- Technique precision and recall; invariant: no inferred edge reported as observed.

## Track E — Measurement and enterprise (P1/P2)

### Phase 54 — Evaluation v2 and the quality dashboard (M)

- New categories: noisy OCR, forged evidence, entity ambiguity, temporal contradictions, conflicting
  authority, hypotheses, challenges, cyber; each reported separately, every figure naming its dataset.
- A quality summary with its formula shown and a trend across committed reports; raw metrics under
  Technical. Model-free benchmarks run in CI.

### Phase 55 — Enterprise controls (L)

- Local authentication (D15); RBAC (Admin, Investigator, Analyst, Reviewer, Auditor, Viewer) from a
  YAML matrix, enforced on every route (route × role test).
- Model router by role and sensitivity (D16); air-gapped mode refusing non-local hosts (tested) and
  shown in the UI; evidence encrypted at rest. ADR-015, ADR-016, a deployment guide.

---

## Order, milestones, dependencies

| Milestone | Phases | What it proves |
|---|---|---|
| M1 — Defensible case | 43, 44, 46, 50, 51 | Evidence with custody, findings that explain themselves, human approval, an exported report |
| M2 — Real investigation | 45, 47, 48, 49 | Sources weighed, explanations tested, findings challenged, plan changes visible |
| M3 — Cyber | 52, 53 | Logs, IOCs, ATT&CK, attack paths with observed and inferred edges |
| M4 — Measured and deployable | 54, 55 | Benchmark v2, quality view, RBAC, routing, air-gap |

44 needs 43; 46 uses 45 (neutral authority until then); 50 needs 44; 51 needs 46 and 50; 47 and 48
feed 51; 53 needs 52; 55 last.

**Risks:** Phases 47, 48 and 53 add model calls per run on `qwen3:4b`; each has a latency budget and a
measurement. Cyber fixtures are synthetic but realistic; ground truth lives only in scenario files.
