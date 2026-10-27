# JARVIS v4 - the product plan (Phases 0-10)

**Status:** agreed 2026-10-26. Not started. Nothing is built until the owner names the phase.

**Why this plan exists.** JARVIS is a product, not a college project. A walk through the console found
that it behaves as a one-pass batch job - create a case, add files, ask once, receive a report - and
that the report reads as raw. Two outside reviews (Gemini, ChatGPT) were checked against the code;
this plan keeps what they got right, corrects what they misread, and adds what neither covered. It
supersedes Part B of `v3-plan-ui-redesign.md` (B1-B5 are done; B6-B10 are folded in below).

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Deployment | **Cloud, GCP, an India region** (`asia-south1` Mumbai or `asia-south2` Delhi). Not air-gapped for now | Data residency for the DPDP Act; a cloud GPU allows a far larger model than the 6 GB laptop |
| First infrastructure | One **L4 (24 GB)** GPU VM running the containers, **Cloud SQL for PostgreSQL** (pgvector), **Cloud Storage** with customer-managed keys for evidence, **Secret Manager**, **Identity Platform** for login. GKE later, with several customers | Matches what JARVIS already uses; simplest thing that is secure |
| Indian languages | **AI4Bharat open-source models first** (IndicTrans2 distilled, their speech models, Indic OCR), running in our cloud. **Bhashini API as an optional second engine** once approved | Same model families as Bhashini; no wait; confidential files never leave our cloud; pinned versions keep receipts reproducible; air-gapped stays possible later |
| Bhashini | Apply now anyway, in parallel | Credibility with government/PSU customers; no GPU cost for permitted files; maintained models |
| Agents | **One orchestrator, a few tools, hard limits** - no swarm | Reliability on a small model; every loop bounded (invariant 7) |
| Order | **Correct answers before polish** | A polished interface around wrong findings is not credible |

**Kept, whatever changes:** evidence first; every claim cites a file and line; a verifier that never
sees the reasoning; confidence computed, never asked for; "what could not be established"; chain of
custody; audit log; the honest benchmark. The work below wraps a conversational experience around
that core - it never replaces it.

## What the reviews got right and wrong (checked against the code)

| Claim | Reality |
|---|---|
| One-pass batch, no conversation | True - the biggest product gap |
| Files chunked, context lost | Partly: reasoning sees budget-limited extracts, not whole files. *Why* B1 lost facts is unmeasured - diagnose first |
| Needs SSE streaming | Progress events already stream with resume; the **answer text** does not |
| Report needs a typed schema | Already typed (`FinalReport`, `InvestigationReport`), facts injected, PDF/DOCX exist. The problem is design and thin prose |
| Hypothesis / adversarial pass | Partly: hypotheses, manual Challenge, gaps. Missing: automatic counter-evidence search |
| Cross-document verification | Missing - the most important engine fix (the B4 gap) |
| Confidence from hard weights | Done, but **not calibrated**; show status labels until it is |
| Hybrid BM25 + vectors + reranker | pgvector exists; BM25 and a reranker do not |
| Page / line coordinates | Page, row and character citations exist; bounding boxes on scans do not |
| Tables into SQL | No - spreadsheets become text rows |
| Versioned findings | Partial: revision numbers, challenge before/after; no case-level history |
| Permissions | Missing entirely |

## The phases

Status: 🟢 exists, upgrade · 🟡 partly exists · 🔴 new

### Phase 0 - Decisions and setup (starts now, in parallel)
- 🔴 Apply for Bhashini
- 🔴 GCP project in an India region; **request GPU quota on day one**; consider Google for Startups credits
- 🔴 Licence register for every shipped model (no non-commercial licences - so no NLLB-200)
- 🔴 Data routing policy by sensitivity, on the composer's existing selector: Confidential / Restricted
  stay in our cloud with our models; Unclassified / Internal may use Bhashini; each organisation can
  tighten it
- 🔴 Pin model versions (LLM, embeddings, vision, speech, translation)

**Done when:** region and GPU are decided, Bhashini applied for, licence register and routing policy written.

### Phase 1 - Secure cloud baseline (nothing goes online before this)
- 🔴 Accounts and login; roles admin / analyst / reviewer / read-only, enforced on every API route
- 🔴 Customer organisations with isolated data
- 🔴 HTTPS; Secret Manager instead of `.env`; encrypted evidence and databases; upload size and type
  checks; rate limits
- 🔴 Containers, scripted infrastructure, one-command deploy and rollback
- 🟡 Encrypted automated backups with a tested restore; health checks; error alerts

**Done when:** nothing is reachable without login, a backup has been restored, a deploy rolled back.

### Phase 2 - Answer quality
- 🔴 Diagnose B1: per-stage logging (extraction -> reasoning -> relevance gate -> verification)
- 🟡 A larger model on the L4, chosen by re-running B1 and the multimodal suite
- 🔴 Whole-document reading when a file fits the context
- 🟡 Hybrid search for large files: BM25 with the existing pgvector search, and a reranker
- 🔴 Cross-document verification (AlignScore / DeBERTa NLI): A in doc 1 + B in doc 2 => C
- 🔴 Automatic counter-evidence search on every material finding
- 🔴 Tables as structured data; totals and reconciliations computed by code
- 🔴 Calibrated confidence; status labels until calibration is shown
- 🟡 Fix the multimodal failures (audio and photo report nothing)

**Done when:** B1 correct facts >= the plain model's, citation precision >= 0.9, zero false alarms,
multimodal suite passes and CI is green.

### Phase 3 - The investigation conversation
- 🔴 A persistent chat thread per case: messages, the findings and evidence each turn used, pins
- 🔴 A bounded tool loop: `search_evidence`, `read_span`, `query_graph`, `calculate`,
  `compare_values`, `verify_claim`, `ask_user`; 4-6 calls per turn; the stop reason recorded; every
  new claim verified before it is shown
- 🔴 References in follow-ups ("recheck F-002 with the new contract") re-check only what is affected
- 🟡 Clarifying questions - a reply box for the existing CLARIFICATION_NEEDED state
- 🟡 Mid-case uploads: custody first, then affected findings marked for re-checking
- 🟡 Finding history: every version, what changed and why, run-to-run comparison

**Done when:** a scripted 5-turn investigation keeps its context, every new claim is verified, and
re-checks leave a before/after record.

### Phase 4 - Responsiveness and workspace
- 🔴 The answer streams word by word over the existing stream; each sentence gets its status mark once checked
- 🟡 A readable activity log from existing events - not the model's raw thinking
- 🟡 Three panes: case and findings / conversation / the existing evidence board
- 🔴 Edit, regenerate, branch, compare runs (stop exists)
- 🟡 Viewer: real PDF page rendering with highlights; zoom on scans with OCR boxes

**Done when:** first words in under 2 s; any citation opens its highlighted source in one click.

### Phase 5 - Professional reports
- 🟢 Template redesign on the existing typed data: executive brief, findings matrix with status
  badges, contradictions side by side with both quotes, timeline, gaps, next evidence, an appendix
  with the receipt and file hashes
- 🟡 One HTML template rendered on screen, to PDF and to DOCX (headless Chromium)
- 🔴 Report versions tied to a case snapshot, each signed with its receipt hash

**Done when:** the four AURORA test reports read like a consultancy deliverable; screen, PDF and DOCX match.

### Phase 6 - Language layer, open-source engine (alongside Phases 3-5)
- 🔴 One language interface: detect, translate, OCR, speech-to-text, text-to-speech, transliterate -
  AI4Bharat models on our GPU (or CPU for translation, if the L4 is full - measured, not guessed)
- 🔴 Evidence-safe translation: line-aligned, the original stays the evidence, citations point at
  original lines
- 🔴 A finding resting only on machine translation needs review; never auto-verified
- 🔴 Viewer: original and translation side by side, cited line highlighted in both
- 🔴 Receipts record the language engine and version
- 🔴 Indian-language benchmark scenarios (e.g. Hindi report vs English ledger; Tamil audio vs minutes)

**Done when:** a cross-language contradiction is found, cited in both languages and verified; the
Indian-language scenarios pass.

### Phase 7 - Bhashini integration (when approval arrives)
- 🔴 Bhashini API client: pipeline discovery, compute calls, retries, timeouts, usage and cost logged
- 🔴 Routing by the Phase 0 policy; automatic fallback to the open-source engine; the receipt names the engine
- 🔴 Ask in any Indian language: typed, Roman-script (transliteration) or spoken
- 🔴 Answers and reports in the user's language; English stays the verified master, translations labelled
- 🔴 Read answers aloud; interface text in Indian languages

**Done when:** an investigation runs end to end in Hindi; switching engines changes only the receipt.

### Phase 8 - Operating as a product
- 🟡 Job queue, concurrent investigations, GPU scheduling
- 🔴 Monitoring: latency, errors, model and Bhashini usage, cost per investigation, a health dashboard
- 🟡 Data governance: retention policies, masking of personal details, DPDP data-subject requests, audit exports
- 🔴 Dependency audit and a penetration test

**Done when:** 10 concurrent investigations run cleanly; cost per investigation is measured.

### Phase 9 - Release discipline and documentation
- 🟡 A release gate in CI: benchmark, multimodal and Indian-language suites, teammate-written
  held-out sets, latency and cost budgets; red blocks a release
- 🔴 User guide, admin guide, API documentation, a security and privacy whitepaper (no "forensic-grade" overclaims)

**Done when:** a release cannot ship with a failing gate; a customer can be onboarded from the docs alone.

### Phase 10 - Breadth
- 🟡 Domain packs in full: entity types, severity rules, report templates
- 🔴 Watch folders and scheduled re-investigation
- 🔴 An on-premise / air-gapped installer, for customers who need it later

## Order

```
Phase 0 -+-> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 8 -> Phase 9 -> Phase 10
         |                 |
         |                 +-> Phase 6 (alongside 3-5)
         +---- Bhashini approval ---------------------> Phase 7 (whenever it arrives)
```

| Phase | Rough size | Why here |
|---|---|---|
| 0 | decisions | Unblocks the cloud and Bhashini |
| 1 | 2 sessions | Nothing online without security |
| 2 | 2-3 sessions | Correct answers before polish |
| 3 | 3 sessions | The biggest change in how it feels |
| 4-5 | 3-4 sessions | The visible upgrade |
| 6-7 | 3-4 sessions | Usable across India |
| 8-9 | 3 sessions | Operable and sellable |
| 10 | ongoing | Breadth after the core is proven |

Each phase: built, tested, documented here under "As built", committed, then paused for the owner's go-ahead.

## As built

### Phase 0 - in progress (2026-10-26)

GCP project **Tessera** (`tessera-jarvis`, Mumbai) created under `chackomartin123@gmail.com`, billing
linked, 11 APIs enabled, ₹5,000/month budget guard. Licence register, pinned versions and routing
policy written. Two items wait on the owner: the paid-account upgrade plus GPU quota (a free trial
cannot attach GPUs), and the Bhashini application. Found: the vision model qwen2.5vl:3b is under a
non-commercial licence and must be replaced before launch. Details: `phase-0-decisions.md`.

### Phase 1a - as built (2026-10-26)

Accounts live in JARVIS's own Postgres (not Identity Platform), so the same product runs in the
cloud, locally and air-gapped. One middleware guards every `/api/` route; a test calls each route
anonymously and expects 401. Roles viewer / reviewer / analyst / admin; `org_id` is on every account
already, for 1c. The audit actor is now the signed-in user, not a header the caller sets.
Deployment shape decided with the owner: **hybrid** - GCP runs the console, backend, databases and
evidence; the laptop's GPU runs the model over Tailscale, so the cloud GPU costs nothing until a
customer needs it.

### Phase 1b - as built (2026-10-27)

Live at https://8.231.91.94.sslip.io on `tessera-vm` (e2-standard-2, asia-south1-a), one Docker
Compose stack: Caddy (automatic HTTPS, security headers) -> backend -> Postgres + pgvector, Neo4j.
Only 80/443 are open; SSH only through IAP. Secrets come from Secret Manager onto the VM, never the
repository. Images are tagged by git commit; `deploy/deploy.sh` deploys HEAD, `deploy.sh rollback`
returns to the previous tag (tested both ways). Nightly backups (database + evidence, runs, traces,
with SHA-256 sums) go to a versioned bucket kept 30 days; a restore is checked before it replaces
anything. The model runs on the laptop over Tailscale (`scripts/expose-ollama-tailscale.ps1`); when
the laptop is off, the console still works and `/health` says `degraded`.
Deferred: a domain name (sslip.io for now), Tailscale ACLs limiting the VM to port 11434, Cloud
Monitoring uptime alerts.

### Phase 1c - as built (2026-10-27)

Each customer is an organisation; the operator's admins (organisation `default`) create one with its
first admin. The organisation rides on the request (a context variable set at sign-in check) and
every store filters by it - runs, cases, evidence, uploads, workspaces, recordings, memory, audit -
with one ownership check in front of every route that names a run, case or evidence item.
Another organisation's resource is 404. Found and fixed on the way: the API accepted file paths as
document names, so a signed-in user could have read any file on the server; it now takes bare names
in the caller's own uploads. Per-account rate limits added. The VM's disk - so Postgres, Neo4j and
the evidence - and the backup bucket are encrypted at rest by Google's default encryption;
customer-managed keys are not set up.
Phase 1 is complete except error alerts (Cloud Monitoring), deferred with the uptime checks.

### Phase 2 - as built (2026-10-27)

Diagnosed stage by stage, the losses were not where B1 suggested: the model read only the last
2,048 tokens of every long prompt (Ollama's default context), the tools showed it values without
their sentences, and two gates discarded correct claims before verification. Fixed those; added
whole-document reading, value-based citation of uncited claims, arithmetic by code, an entailment
model (DeBERTa, ONNX, CPU) as a third verifier, automatic counter-evidence on every verified finding,
hybrid BM25 + vector search, Indian number formats, and evidence labels in place of percentages.
Benchmark: correct facts 0.444 -> 0.900 (plain model 0.978), supported sentences 0.917 (plain
0.577), invented values 0 (plain 2), citation precision 0.775 (plain 0.744), no false alarms.
Not yet at the bar (correct >= plain, citation precision >= 0.9); the larger model waits on the GPU.

### Phase 3a - as built (2026-10-27)

A thread per case, kept beside the run archives in a folder per organisation. Each message runs a
bounded loop (five tool calls) over the case's documents and findings - search, read a span, query
findings, calculate, compare, ask the person - and every claim of the answer is resolved to lines of
the case and verified before it is shown. "Recheck F-002" re-verifies that finding and records
before/after. Small cases are given to the model whole: with searched lines alone it answered
nothing to two of three live questions. `query_graph` became `query_findings` (the case's verified
claims); `verify_claim` is not optional for the model - the service verifies every claim.

### Phase 3b - as built (2026-10-27)

A run that asks a question gets a reply box; the answer starts it again with the same documents and
case. Each finding has a history assembled from what the run, reviews, challenges and the
conversation already record. Two runs of a case compare finding by finding. Evidence added to a case
after a run marks that run's findings for re-checking (computed from custody times, not a flag that
could go stale). **Phase 3 is complete.**

### Phase 4 - as built (2026-10-27)

The conversation streams over SSE: activity in words at once, the answer's words when the model
has written them, each claim's mark when checked. Answers regenerate and messages edit, keeping what
they replace; investigations re-run as-is or edited. Conversation citations open the cited line in a
drawer. Measured: activity < 0.1 s, answer words 9-21 s on qwen3:4b - the 2 s bar holds for the
activity line only, and waits on the larger model. Deferred: three panes, rendered-PDF highlights.

### Phase 5 - as built (2026-10-27)

One designed document built from the typed report - brief, findings matrix, contradictions quoted
side by side, timeline, gaps, appendix with receipt and file hashes - drawn as HTML, PDF (ReportLab,
not headless Chromium: a 300 MB browser in the image for text and tables was not worth it) and DOCX.
Every export is a numbered version signed with the content, receipt and case-snapshot hashes.
Remaining: reading it against the four AURORA test reports, locally, with the owner.
