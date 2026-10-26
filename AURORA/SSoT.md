# AURORA — Single Source of Truth (SSoT)

> **This file is the authoritative context for the AURORA project.** Any human or AI agent reading this file alone has the full combined context of every source document in the project. Where this file and any source document disagree, **this file wins** — the source documents are bid artefacts frozen at submission, this file tracks current truth.

---

## 0. Document Governance

### 0.1 Document status

| Field | Value |
|---|---|
| Document title | AURORA — Single Source of Truth |
| Version | 1.0 |
| Status | Active — bid baseline |
| Last updated | 2026-08-08 |
| Next review date | On MDL award decision, or 2026-09-30, whichever is earlier |
| Confidentiality | **Internal — Arcaisys only.** Contains candid maturity, gap and risk assessments not suitable for external circulation. Not to be shared with MDL in this form. |
| Intended readers | Arcaisys team; AI agents working on AURORA |
| Document owner | *Not yet assigned — see §32* |
| Approvers | *Not yet assigned — see §32* |

### 0.2 Source-of-truth rules

1. **This file is authoritative** for all current project facts.
2. Where a source document contradicts this file, this file is correct and the source document is stale. Stale positions are recorded in §42 (Superseded Information) so the discrepancy is visible, never silently dropped.
3. **MDL-issued documents are authoritative for requirements.** Arcaisys cannot unilaterally change what the SoW requires. Where an Arcaisys proposal document promises something the SoW does not require, that is a *commitment*, not a requirement, and is marked as such.
4. **Nothing in this file is a commitment to MDL** unless it also appears in a submitted bid document. This file contains internal decisions taken after submission.
5. Blank sections are marked `> **Not yet defined.**` with the reason and the trigger that will fill them. A blank section is a known gap, never an oversight.

### 0.3 Information authority hierarchy

Highest authority first. In any conflict, the higher entry wins.

| Rank | Source | Authority over |
|---|---|---|
| 1 | Annexure-I SoW / PRD (MDL, rev 00, 13 Jul 2026) | Requirements, scope, acceptance criteria, delivery phases, KPIs |
| 2 | MDL PS-71 problem brief (Sl. No. 71) | The three Tasks to Perform; problem framing |
| 3 | Annexure-II Technical Questionnaire (as submitted) | Technology and AI model disclosure, security posture, compliance matrix commitments — these were submitted for security clearance and bind us |
| 4 | This SSoT | All post-submission decisions; technology selections; internal planning |
| 5 | AURORA Annexure 1 & Annexure 2 (as submitted) | Solution design detail, deliverable definitions D-01→D-15 |
| 6 | Arcaisys Concept Note | Elaboration and narrative; lowest technical authority |
| 7 | Detailed Project Timeline | Phase and milestone structure (12-month plan) |
| 8 | ROI / Market Potential documents | Commercial narrative only. **No technical authority.** |

### 0.4 Conflict resolution rules

- **Requirement conflict** (two MDL documents disagree) → raise with MDL, do not resolve internally. Log in §43.
- **Design conflict** (two Arcaisys documents disagree) → resolve internally, record the decision in §41.1, record the superseded position in §42.
- **Requirement vs design conflict** → the requirement wins; redesign.
- **Commitment vs feasibility conflict** (we promised something we now doubt) → escalate immediately; do not quietly de-scope a submitted commitment. Log in §43.

### 0.5 Update protocol

1. Any change to project truth updates this file **first**, before code, before slides, before client documents.
2. Every substantive change adds a row to §41.2 (Change Log).
3. Every decision adds a row to §41.1 (Decision Log) with rationale and alternatives considered.
4. Anything this file supersedes moves to §42 — never deleted, because the stale version is still sitting in a document MDL holds.
5. Version increments: `X.0` on award/phase transition, `X.Y` on substantive change, no increment for typo fixes.

### 0.6 Review cadence

| Trigger | Action |
|---|---|
| MDL award decision | Full review; version → 2.0; re-baseline as execution document |
| Phase gate (RG-1 → RG-4) | Full review of affected sections |
| Any MDL direction received on an open item (§43) | Immediate update of the affected section |
| Otherwise | Monthly |

---

## 1. Executive Summary

AURORA (**A**utomated **U**nified **R**easoning and **O**ptimization **A**rchitecture) is an on-premise, air-gapped engineering decision-support platform proposed by Arcaisys to Mazagon Dock Shipbuilders Limited under iDEX DRISHTI Problem Statement 71.

Naval ship design at MDL currently depends on manual cross-verification between CAD models, BOMs, classification rule libraries and drawings. Roughly 25% of engineering changes occur after contract design finalisation, and each one propagates unpredictably across hull, propulsion, weapons and other systems. Validation cycles run into weeks; 3D-to-BOM reconciliation is manual and a persistent source of human error.

AURORA unifies CAD data, BOM records, classification rules, simulation references and engineering dependencies into one traceable environment, then automates four things over it: **CAD–BOM discrepancy detection**, **multi-society compliance validation with clause-level citation**, **dependency-aware change impact propagation**, and **drawing revision synchronisation** through to production release.

The architecture is **deterministic-first**. Every compliance determination is produced by a rule engine, is reproducible, and cites the specific clause it came from. Machine learning is used selectively and only where it demonstrably beats a deterministic baseline — principally CAD–BOM match confidence scoring. A GenAI/RAG layer exists but is explicitly non-core and never produces an engineering determination. Final engineering authority, certification and production release always rest with designated MDL personnel.

**Current position:** bid submitted, awaiting MDL decision. Product maturity is **Research** — zero production installations, and every row of the Functional Compliance Matrix is marked "New Development Required". Twelve of those rows are nonetheless committed as working at MVP. That gap is the single largest execution risk on this programme and is tracked as R-01 in §12.

---

## 2. Project Identity

| Field | Value |
|---|---|
| Product name | AURORA — Automated Unified Reasoning and Optimization Architecture |
| Programme | iDEX DRISHTI Innovation Challenge |
| Problem Statement | PS-71 / Sl. No. 71 — "AI tool for optimization of design w.r.t. Class rules, standards, regulations etc. and synchronize 3D models with Bill of Material (BOM) to eliminate human errors" |
| Challenge reference | iDex\71\2026 |
| Issuing authority | Mazagon Dock Shipbuilders Limited (MDL), Ministry of Defence, Government of India |
| Customer address | Dockyard Road, Mumbai 400010 |
| SoW document | Annexure-I, Rev 00, dated 13 Jul 2026, 15 pages |
| Bidder | Arcaisys |
| Bidder address | G1603, Samarth Garden, Bhandup (W), Mumbai 400078, Maharashtra |
| Applicant name | Leejo Purvathan |
| Contact | pm.team@arcaisys.com · 9137815600 / 9029767757 |
| Website | arcaisys.com |
| Duration | 12 months from contract award |
| Deployment model | Fully on-premise, air-gapped |
| Technical validation partner | CDAC-Mumbai (senior faculty review; collaboration anticipated, not contracted) |

---

## 3. Strategic Context

### 3.1 Vision

An engineering intelligence layer that sits above the shipyard's existing CAD, PLM and ERP systems and makes the current configuration state of a vessel programme continuously knowable — so that no engineering change reaches production carrying an undetected compliance violation or an unreconciled BOM.

### 3.2 Mission

Convert MDL's manual, expertise-dependent design validation workflow into a structured, traceable and accelerated process, without ever removing engineering judgement from the decision.

### 3.3 Strategic rationale

- **For MDL:** validation cycle compression from weeks to hours, earlier detection of propagated impact, and long-term retention of engineering knowledge that currently lives in individual heads.
- **For Arcaisys:** AURORA is a horizontal engineering-intelligence platform. The naval shipbuilding instance is the beachhead; the same architecture applies to aerospace, energy, heavy engineering, rail and any regulated engineered-product industry. Defence deployment establishes the security and assurance credentials that unlock those.
- **For the ecosystem:** an indigenous, air-gapped alternative to foreign engineering-compliance tooling, aligned with IndiaAI Mission objectives and GoI data sovereignty policy.

### 3.4 Historical context

MDL's brief cites commercial project data showing ~25% of changes occurring post contract-design finalisation. The enabling shift — LLMs, RAG, knowledge graphs and mature engineering-data integration — is what makes rule interpretation, cross-discipline impact prediction and 3D–BOM reconciliation automatable now when they were not previously. This is MDL's own stated "Why Now" (SoW §2.3).

---

## 4. Problem Statement

### 4.1 As stated by MDL

Develop an AI-powered system that analyses detail design parameters against class rules, standards and regulations; predicts downstream impacts across disciplines (hull, propulsion, weapons and concerned systems, including structural re-analysis / weight redistribution and re-qualification / trials); and provides intelligent inputs towards finalisation of detail design, incorporation into basic drawings before class submission, and incorporation of the latest class-approved revision into production drawings post-approval. The system shall additionally synchronise 3D models with the BOM to eliminate human errors.

### 4.2 The three Tasks to Perform

Everything AURORA does must ultimately serve these three. They are the acceptance frame.

| Task | Statement | AURORA coverage |
|---|---|---|
| **T1** | Build AI models to highlight changes in design drawings w.r.t. classification rules, integration requirements, regulatory requirements | Change-triggered compliance mode (§22 `CMP`), clause-cited findings, drawing diff |
| **T2** | Develop an intelligent system to incorporate the changes in detail design in the 3D model | **Partial by design.** AURORA detects CAD↔BOM divergence, updates BOM from CAD, and triggers CAD re-export via webhook. It does **not** write geometry back into the CAD model. See §43 OQ-03 — this interpretation is unconfirmed with MDL. |
| **T3** | Develop an intelligent system to reflect changes in approved drawings in production drawings | Drawing synchronisation & revision engine (§22 `DRW`), production release queue |

### 4.3 Operational pain (the real problem)

- Engineering changes are never isolated; one modification affects multiple disciplines and no engineer can manually trace every downstream dependency.
- Impact assessment depends on individual experience — slow, and vulnerable to missed dependencies when experienced staff rotate off.
- 3D↔BOM consistency degrades continuously; errors surface at procurement, fabrication or assembly, when they are expensive.
- Compliance verification against class rules is manual, repeated per revision, and consumes senior engineer time.
- Late discovery of conflicts forces redesign, re-documentation, re-approval and sometimes rework of completed physical work.
- Configuration control degrades as revision count grows; production can end up building to a superseded configuration.

### 4.4 Root causes

| Root cause | Consequence |
|---|---|
| Engineering artefacts live in disconnected systems | Cross-verification can only be manual |
| Dependencies exist only as tacit expertise | Impact analysis is not repeatable or auditable |
| Class rules are dense prose, not machine-readable | Compliance checking cannot be automated without digitisation |
| No single component identity spanning CAD and BOM | Reconciliation has no reliable join key |
| Revision state is tracked per-artefact, not per-configuration | Drawings drift out of sync with the approved model |

---

## 5. Current State, Target State, Migration

### 5.1 Project current state

**Bid submitted; awaiting MDL decision.** No contract, no kickoff, no Month 0. Nothing in this document commits spend or resource until award.

| Dimension | State |
|---|---|
| Product maturity | **Research.** 0 production installations. No comparable deployment elsewhere. No version history. |
| Codebase | None specific to AURORA. Architecture is designed, not built. |
| Feature compliance | All 26 Functional Compliance Matrix rows = "New Development Required". None available out-of-the-box, none achievable by configuration of an existing product. |
| Evidence base | Six prior projects submitted (2 domain, 4 closely-aligned) — see §39.3. Includes **IRS ship auditing software for IRCLASS**, which is directly classification-society domain and on-prem |
| Domain validation | Solution reviewed by senior faculty at CDAC-Mumbai |
| Team | Not yet staffed — see §32 |

### 5.2 MDL as-is process (factual, per SoW §7)

- Detail design produced across disciplines per contract requirements.
- Compliance checked **manually** by engineers referencing rule documents.
- Post-contract changes assessed for cross-discipline impact by **expert judgement**, discipline by discipline.
- 3D models and BOM maintained and reconciled **manually**.
- Finalised design incorporated into basic drawings → submitted to class → on approval, revision incorporated into production drawings — **largely manual**.

Lifecycle: contract design → detail design → basic drawings (to class) → class approval → production drawings.

### 5.3 Target state

The same lifecycle, with AURORA as a validation and traceability layer over it:

- Single unified component identity spanning CAD, BOM, rules and drawings.
- Compliance checked automatically, clause-cited, on every change — not once per review cycle.
- Change impact computed by graph traversal in seconds, not reconstructed by expert recall.
- CAD↔BOM divergence surfaced continuously with confidence scores.
- Drawing revision propagation automated through to a production-release queue.
- Complete immutable audit trail from determination → disposition → approval → drawing incorporation.
- Engineering authority unchanged: humans approve, the system advises.

### 5.4 Migration strategy

No data migration in the conventional sense — AURORA reads from existing systems and does not replace them. Adoption is phased:

| Step | Content |
|---|---|
| 1 | Phase 0 assessment: CAD format audit, PLM/ERP interface specs, network topology, BOM schema alignment, historical data availability |
| 2 | Pilot on one discipline/system, subset of rules, historical scenarios — runs alongside existing manual process, does not replace it |
| 3 | Expand disciplines and rule coverage; manual process becomes the check on AURORA rather than the primary path |
| 4 | Air-gapped production deployment at full project scale; manual cross-verification retained only for exception handling |

**No big-bang cutover.** The existing manual process remains the fallback throughout.

---

## 6. Objectives & Scope

### 6.1 Objectives (SoW §4)

| # | Objective | Expected outcome |
|---|---|---|
| O1 | Automate design compliance checking against class rules/standards/regulations | Faster, consistent, clause-referenced compliance assessment |
| O2 | Predict downstream cross-discipline change impacts early | Fewer late-discovered propagated impacts |
| O3 | Synchronise 3D models with BOM | Elimination of human errors from 3D–BOM inconsistencies |
| O4 | Provide intelligent inputs for design finalisation and drawing incorporation | Smoother basic-drawing → class → production-drawing flow |
| O5 | Reduce rework and rework-driven wastage | Measurable reduction against the ~25% post-contract-change baseline |
| O6 | Operate securely in a Defence environment | Fully on-premise / air-gapped, auditable, access-controlled |

### 6.2 In scope (SoW §5.1)

- Ingestion of detail design parameters, 3D CAD models and BOM.
- Ingestion and structuring of applicable class rules, standards and regulations.
- Automated compliance checking and design-optimization suggestions with clause-level references.
- Downstream change-impact prediction across disciplines.
- 3D model ↔ BOM synchronisation and mismatch detection.
- Support to design finalisation, incorporation into basic drawings before class submission, and incorporation of class-approved revisions into production drawings.
- Revision/version management, review/approval workflow, reporting.
- On-premise / air-gapped deployment with security, access control and audit.

### 6.3 Out of scope (permanent)

| Item | Rationale | Source |
|---|---|---|
| Issuing formal class certification or approval decisions | Retained by classification society and design authority | SoW §5.2 |
| Procurement of PLM / ERP / CAD licences or physical infrastructure | Customer responsibility | SoW §5.2 |
| Running FEA/CFD solvers as such | System flags where re-analysis is required; solver execution may be offered but is not mandated | SoW §5.2 |
| Automated submission to classification-society portals | Package preparation only; submission remains a controlled manual activity | SoW §5.2 |
| Autonomous approval of any engineering decision | Human authority is architecturally mandatory | HITL layer |

### 6.4 Conditional scope (pending MDL decision)

**As-installed / as-built registration** — point cloud (E57/LAS/PTS), photogrammetry, imagery, and registration to the design coordinate system. Currently marked "NO" in Functional Compliance Matrix rows 3–5, but **not finalised**. May or may not enter scope. Captured as features F-CND-01→06 (§22.24). If confirmed, requires separate scope, cost and schedule agreement — it is a material addition to a 12-month plan. If declined, the CV/3D components (YOLOv11, SAM 2, Open3D, PDAL, VTK) should be reviewed for removal from the §8.2 disclosure, since claiming unused capability is a liability.

**Drawing format coverage** — awaiting MDL direction. Working assumption in §22.24.2.

### 6.5 Designed-for extensibility (future, not committed)

Simulation-assisted optimisation with PyTorch surrogate models; multi-vessel-programme scale-out; enterprise HA cluster at full-ship scale; cross-industry verticalisation (aerospace, energy, rail, heavy engineering).

---

## 7. Stakeholders, Users & Personas

### 7.1 Stakeholder register

| Stakeholder | Role in the process | Interaction with AURORA |
|---|---|---|
| Detail Design Engineers (Hull/Structural, Propulsion, Weapons, Electrical, Auxiliary Systems) | Develop and modify detailed designs | Upload/update CAD, review compliance findings, receive optimisation recommendations, resolve 3D–BOM mismatches, analyse downstream impact, act before submission |
| Design Managers / Chief Designer | Approve engineering decisions, resolve cross-disciplinary conflicts, finalise designs | Monitor via dashboard, review impact assessments, evaluate optimisation output, approve/reject changes, authorise baselines |
| Classification & Regulatory Liaison | Ensure compliance before submission | Validate clause-referenced compliance reports, prepare submission packages, review non-compliances, track approval status |
| Configuration / Revision Control Engineers | Maintain versioned engineering data | Manage revision history, compare versions, synchronise CAD↔BOM, control baseline release |
| Production Planning / Drawing Office | Convert approved designs to production documentation | Verify released drawings match approved revisions, confirm BOM consistency, generate production-ready documentation |
| Quality Assurance Engineers | Verify quality, compliance and traceability | Review compliance reports, validate evidence, audit decisions, verify reconciliation results |
| IT / Cybersecurity Administrators | Deploy, secure and maintain the platform | Configure roles, integrate PLM/CAD/ERP, monitor audit logs, manage security, backups |
| MDL Programme Authority | Award, gate reviews, final acceptance | Review-gate approvals RG-1→RG-4, final acceptance certificate |
| Classification Societies (IRS, LR, DNV, BV, ABS) | External approval authority | Indirect — receive submission packages, raise queries which AURORA ingests |
| Arcaisys delivery team | Build and deliver | — |
| CDAC-Mumbai | Technical validation partner | Advisory; not contracted |

### 7.2 Personas

**P1 — Detail Design Engineer.** High CAD fluency, low tolerance for tools that add clicks without removing work. Judges AURORA on whether a compliance finding is *actionable*: does it tell me the actual value, the limit, and the clause? Will abandon the tool if it produces findings he must then manually verify. **Design implication:** every finding shows actual value, allowable limit, units and clause ID in plain engineering terms — never an abstract score.

**P2 — Classification Liaison.** Lives in rule documents. Needs defensibility above all — must be able to answer a society query with evidence. **Design implication:** clause citation is non-negotiable; the submission package must be assembled, not compiled by hand.

**P3 — Design Manager.** Sees volume, not detail. Needs to know what is blocked, what is risky, and what needs a decision today. **Design implication:** dashboard-first, severity-ranked, drill-down on demand.

**P4 — Configuration Control Engineer.** Cares only about whether the right revision is in the right place. **Design implication:** drawing status taxonomy, diff views, baseline tags.

**P5 — IT / Cyber Administrator.** Will block deployment if anything phones home. **Design implication:** zero outbound network, full component country-of-origin disclosure, SBOM, offline update path.

**P6 — QA Engineer.** Audits after the fact. **Design implication:** immutable, hash-chained, exportable audit trail.

---

## 8. Use Cases & User Workflows

### 8.1 Primary use cases

| ID | Use case | Primary actor | Trigger |
|---|---|---|---|
| UC-01 | Validate a design change against class rules | Detail Design Engineer | CAD revision saved |
| UC-02 | Detect and resolve CAD–BOM discrepancies | Detail Design Engineer / Config Control | Scheduled sync or BOM update |
| UC-03 | Assess downstream impact of a proposed change | Detail Design Engineer | Change request raised |
| UC-04 | Run a full baseline compliance scan | Classification Liaison | New project, or major rule catalog update |
| UC-05 | Generate a classification society submission package | Classification Liaison | Pre-submission gate |
| UC-06 | Resolve a society query and re-submit | Classification Liaison | Query received from society |
| UC-07 | Propagate an approved revision into production drawings | Drawing Office | Class approval received |
| UC-08 | Explore design alternatives under weight/cost/compliance trade-off | Detail Design Engineer | Optimisation requested |
| UC-09 | Approve or reject a change with justification | Design Manager / Approver | Review queue item |
| UC-10 | Audit a past engineering decision | QA Engineer | Audit or investigation |
| UC-11 | Update the rule catalog for a class rule revision | Admin + SME | Society publishes rule update |
| UC-12 | Compare two design baselines | Config Control Engineer | Version comparison request |

### 8.2 Canonical operational workflow (8 stages)

| Stage | Activity |
|---|---|
| 1 — CAD & BOM Ingestion | Updated CAD assemblies and BOM datasets ingested and linked to the Unified Component Registry |
| 2 — CAD–BOM Synchronisation | Automated reconciliation; discrepancies surfaced for review |
| 3 — Change Impact Analysis | Dependency-aware traversal identifies affected components, subsystems and downstream domains |
| 4 — Compliance Validation | Rules associated with impacted systems re-evaluated; findings consolidated |
| 5 — Engineering Optimisation *(optional)* | Comparative trade-off analysis and alternative configuration evaluation |
| 6 — Drawing Synchronisation | Associated drawings and revision-controlled documentation updated to the approved design state |
| 7 — Classification Submission | Findings, compliance summaries and supporting documentation assembled for submission |
| 8 — Approval & Audit Archiving | Approved actions, revision history, compliance records and decisions archived |

Human review and approval checkpoints are present at every stage. There is no path through this workflow that reaches production without an authorised human approval.

### 8.3 Automated drawing-revision sequence

Triggered automatically on detected design change:

1. CAD geometry/topology hash change detected by CAD Parsing Engine.
2. Impact Propagation Engine identifies affected components.
3. CAD–BOM Sync Engine updates BOM entries for affected components.
4. Compliance Engine validates updated parameters against the rule catalog.
5. System flags all drawings linked to affected components via PLM metadata.
6. Drawings flagged `PENDING_APPROVAL`; draft change record generated.
7. **Engineer review and approval checkpoint** — approve, reject, or add justification.
8. Drawing revision incremented (Rev N → Rev N+1) with change delta logged.
9. Approved drawings pushed to the production release queue as a "Ready for Production" package.

### 8.4 Worked scenario (validated example)

**Structural reinforcement change, engine room bulkhead ER-BH-204.** IRS flags plate thickness below revised rule limit.

| Step | Panel | Outcome |
|---|---|---|
| 1 | System Health | Engines active; BOM 1 day stale → freshness alert → engineer triggers BOM refresh |
| 2 | Impact Analysis | Thickness 12mm → 16mm. **48 impacted components.** Adjacent stiffeners HIGH, cable trays MEDIUM, ventilation ducts LOW |
| 3 | CAD–BOM Sync | `MASS_MISMATCH` Δ+8.5%, `MATERIAL_MISMATCH`. Match confidence 0.91 → auto-match valid. Engineer runs "Update BOM from CAD", flags 2 for manual review |
| 4 | Compliance | Original violation resolved (PASS). **New**: adjacent support beam stress exceeds limit (FAIL); cable tray clearance (WARNING). Fixing one rule created two secondary issues |
| 5 | Drawing Sync | 6 drawings `STALE`; auto-revision Rev 2 → Rev 3; diff view shows thickness and support geometry changes; engineer approves for production |
| 6 | Classification | Package submitted to IRS; IRS queries justification for increased beam load; engineer attaches impact and compliance reports; re-submission readiness confirmed |
| 7 | Optimisation | Pareto shows alternate material −6% weight / +3% cost; **engineer rejects, retains approved design** |

This scenario is the reference for acceptance demonstration. Step 4 is the value proposition in one line: *the system caught that fixing one rule broke two others.*

---

## 9. Requirements

### 9.1 Business requirements

| ID | Requirement | Source |
|---|---|---|
| BR-01 | Reduce manual compliance-checking effort against the current baseline | SoW O1, K3 |
| BR-02 | Reduce rework driven by late-discovered change propagation, against the ~25% post-contract-change baseline | SoW O5, K4 |
| BR-03 | Eliminate human errors arising from 3D–BOM inconsistency | SoW O3, K5 |
| BR-04 | Improve first-pass class approval rate and shorten approval cycles | ROI §2C |
| BR-05 | Preserve institutional engineering knowledge across vessel programmes and staff turnover | Concept Note §7.4 |
| BR-06 | Operate lawfully and securely within a Defence shipyard: air-gapped, sovereign, auditable | SoW O6, NFR-01/02/03 |
| BR-07 | Avoid vendor lock-in; integrate with rather than replace existing CAD/PLM/ERP | NFR-11 |

### 9.2 Functional requirements (SoW §8) — authoritative

`M` = Mandatory, `D` = Desirable.

**9.2.1 Data Ingestion & Knowledge Base**

| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Ingest detail design parameters (from CAD/PLM/spreadsheets) | M |
| FR-02 | Ingest 3D CAD/production models (e.g. STEP, IGES, IFC, native 3D) | M |
| FR-03 | Ingest / parse the Bill of Material from ERP/PLM/spreadsheet | M |
| FR-04 | Ingest & structure class rules / standards / regulations (including scanned/PDF via OCR) | M |
| FR-05 | Build & maintain a searchable, versioned knowledge base of rules/standards | M |

**9.2.2 Compliance Analysis & Optimization**

| ID | Requirement | Pri |
|---|---|---|
| FR-06 | Automatically check design against class rules/standards/regulations | M |
| FR-07 | Flag non-compliances with citation to the specific rule/clause | M |
| FR-08 | Provide design-optimization suggestions w.r.t. class rules/standards | D |
| FR-09 | Assign a confidence score to each compliance/optimization output | M |

**9.2.3 Change Impact Prediction**

| ID | Requirement | Pri |
|---|---|---|
| FR-10 | Predict downstream change impacts across disciplines (hull, propulsion, weapons, systems) | M |
| FR-11 | Flag structural re-analysis / weight-redistribution impacts | M |
| FR-12 | Flag re-qualification / testing & trials impacts | M |

**9.2.4 3D–BOM Synchronization**

| ID | Requirement | Pri |
|---|---|---|
| FR-13 | Check consistency between the 3D model and the BOM | M |
| FR-14 | Detect 3D–BOM mismatches (missing/extra items, quantity or specification differences) | M |
| FR-15 | Maintain traceability: design parameter ↔ rule ↔ BOM item ↔ 3D model | M |

**9.2.5 Design Finalisation & Revision Workflow**

| ID | Requirement | Pri |
|---|---|---|
| FR-16 | Support incorporation of finalised design into basic drawings before class submission | M |
| FR-17 | Manage revisions/versions of design, basic drawings and production drawings | M |
| FR-18 | Incorporate the class-approved revision into production drawings post-approval | M |
| FR-19 | Provide a review & approval workflow with disposition (accept / reject / refer) | M |

**9.2.6 Explainability, Reporting & Governance**

| ID | Requirement | Pri |
|---|---|---|
| FR-20 | Provide explainability with source citations for every determination (anti-hallucination) | M |
| FR-21 | Generate compliance / impact / BOM-sync reports | M |
| FR-22 | Provide dashboards / analytics (change volume, compliance status, impact) | D |
| FR-23 | Export reports to PDF and standard interchange formats | M |
| FR-24 | Role-based user and access management | M |
| FR-25 | Maintain a complete audit trail of user/system actions | M |
| FR-26 | Provide REST API / interfaces for integration with PLM/CAD/ERP and shipyard systems | D |

### 9.3 Non-functional requirements (SoW §9) — authoritative

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Deployment | Must run fully on-premise and support air-gapped / offline operation with no internet dependency at install-time or run-time |
| NFR-02 | Data Sovereignty | No component (model, library, licence check, telemetry, cloud service) may route, store or process data in — or be controlled from — a country sharing a land border with India. Country of origin of all components must be disclosed |
| NFR-03 | Security | Encryption at rest and in transit; local/AD/LDAP authentication; RBAC; comprehensive audit logging; protection of licensed class-rule content; compliance with applicable GoI / CERT-In cybersecurity guidelines |
| NFR-04 | Trustworthiness | Every compliance determination must be grounded in and cited to an authoritative rule/clause; unsourced or hallucinated determinations are unacceptable. Accuracy to meet jointly agreed targets on pilot data |
| NFR-05 | Performance | Assess a defined design/change set within an agreed time window; support batch processing of large rule sets, BOMs and models |
| NFR-06 | Scalability | Scale across disciplines and large rule/BOM/model volumes without architectural redesign |
| NFR-07 | Explainability & Traceability | Each output must be explainable and traceable to its rule, BOM item and/or model evidence |
| NFR-08 | Usability | Usable by design and configuration engineers with minimal training; clear, reviewable output |
| NFR-09 | Data Currency | The rule/standard knowledge base must be updatable (with versioning) as regulations and class rules are revised, without vendor code changes where feasible |
| NFR-10 | Maintainability | Modular, documented and supportable within the shipyard; configurable rules/thresholds |
| NFR-11 | Interoperability | Consume standard design/model/BOM/rule formats and integrate with PLM/CAD/ERP; avoid proprietary lock-in where open standards exist |
| NFR-12 | Auditability | Immutable record from determination → disposition → approval → drawing incorporation |

### 9.4 Functional Compliance Matrix — as submitted (binding)

These are commitments made to MDL. `MVP` = committed to work at MVP stage; `Post-Dev` = committed after full development. **Every row is "New Development Required"** — nothing exists today.

| # | Feature | MVP | Post-Dev | Notes |
|---|---|---|---|---|
| 1 | Ingest 2D production drawings (PDF/TIFF/DWG/DXF) | YES | YES | Document ingestion and parsing to be developed |
| 2 | Ingest 3D CAD models (STEP/IGES/IFC/native) | YES | YES | Requires CAD integration layer |
| 3 | Ingest as-installed point cloud (E57/LAS/PTS) | NO | NO | **Now conditional** — see §6.4 |
| 4 | Ingest photographs / images of installation | NO | NO | **Now conditional** — see §6.4 |
| 5 | Register/align as-installed data to design coordinates | NO | NO | **Now conditional** — see §6.4 |
| 6 | Recognise affected systems | YES | YES | Knowledge-graph driven impact analysis |
| 7 | Recognise ventilation / HVAC duct systems | NO | YES | Domain-specific engineering modelling |
| 8 | Recognise equipment / machinery | NO | YES | Entity extraction and dependency mapping |
| 9 | Detect route change (pipe/duct rerouting) | NO | YES | Requires CAD topology analysis |
| 10 | Detect equipment relocation | YES | YES | Dependency and location comparison |
| 11 | Detect missing components | NO | YES | Requires CAD comparison |
| 12 | Detect added / extra components | NO | YES | Requires CAD comparison |
| 13 | Quantify dimensional / positional deviation | NO | YES | CAD comparison module |
| 14 | Classify deviation severity against tolerances | YES | YES | Constraint validation engine |
| 15 | Confidence score | YES | YES | Risk scoring engine |
| 16 | Visual overlay of the system | NO | YES | Dashboard visualisation |
| 17 | Automatic report generation | YES | YES | Impact assessment reports |
| 18 | Export / hand-off to design department | YES | YES | PDF/export package generation |
| 19 | Revision / version comparison of drawings | NO | YES | Design baseline comparison |
| 20 | Review & approval workflow | YES | YES | Engineering change approval workflow |
| 21 | Role-based user & access management | YES | YES | RBAC implementation |
| 22 | Audit trail | YES | YES | Complete activity traceability |
| 23 | Dashboard / analytics | YES | YES | Unified management dashboard |
| 24 | Export to PDF / standard formats | YES | YES | Standard reporting exports |
| 25 | REST API for integration | YES | YES | Integration architecture |
| 26 | Offline / air-gapped operation | YES | YES | Designed for on-prem deployment |

**12 rows committed at MVP, from a zero codebase, inside a 6-month Phase 1.** This is R-01.

---
## 10. Success Criteria, KPIs & Acceptance

### 10.1 MDL success metrics (SoW §12)

| # | Metric | Target |
|---|---|---|
| K1 | Compliance-check accuracy (precision/recall vs expert review) | Jointly agreed thresholds |
| K2 | Citation correctness / traceability of determinations to authoritative clauses | High, jointly agreed |
| K3 | Reduction in manual compliance-checking man-hours | Measurable reduction vs baseline |
| K4 | Reduction in change-propagation errors / rework | Measurable reduction against ~25% baseline |
| K5 | 3D–BOM mismatch detection rate / reduction in BOM errors | Measurable reduction in human errors |
| K6 | Time to assess a design change's downstream impact | Significantly faster than manual |
| K7 | Auditable trail from determination → approval → drawing incorporation | 100% auditable |

### 10.2 Arcaisys committed performance targets

| ID | Target | Trace |
|---|---|---|
| PT-01 | CAD–BOM match **precision ≥ 90%** on pilot validation data | K5, D-14 |
| PT-02 | CAD–BOM match **recall ≥ 90%** on pilot validation data | K5, D-14 |
| PT-03 | Compliance validation **agreement with SME ≥ 85%** | K1, D-14 |
| PT-04 | **Zero critical compliance false negatives** within validated rule scope | K1, D-14 |
| PT-05 | Assisted CAD–BOM validation agreement with SME ≥ 90% | Concept Note §3.6 |
| PT-06 | Intelligent discrepancy prioritisation accuracy ≥ 85% vs SME criticality | Concept Note §3.6 |
| PT-07 | Optimisation recommendation relevance ≥ 80% positive reviewer evaluation | Concept Note §3.6 |
| PT-08 | Explainability & traceability coverage = **100%** of analytical outputs | NFR-07 |
| PT-09 | Knowledge graph completeness ≥ **95%** of BOM line items with ≥1 dependency edge, before go-live | Concept Note §3.5 |
| PT-10 | Change impact analysis response in **seconds** for standard subsystem propagation | K6, NFR-05 |
| PT-11 | Compliance delta validation within **minutes** for isolated modifications | NFR-05 |
| PT-12 | Full baseline compliance evaluation within operationally practical review timelines | NFR-05 |
| PT-13 | Validation cycle reduction from **weeks to hours** (programme-level objective) | Executive summary |

> **Internal note.** PT-04 (zero critical false negatives) is an absolute claim and the most dangerous commitment in the bid. It is achievable only *within validated rule scope* — that qualifier must never be dropped in any client-facing restatement. Rule digitisation quality is what determines whether PT-04 holds; see R-03.

### 10.3 Acceptance criteria (SoW §14)

**Capability Demonstration / MVP**
- Performs an automated compliance check that flags a non-compliance and cites the specific clause on a representative sample, **or** detects a 3D–BOM mismatch.
- Runs without internet dependency (or a clearly evidenced offline path).

**Full System**
- Satisfies all mandatory functional requirements (FR marked M) and all NFR-01→NFR-12.
- Meets agreed accuracy and citation-correctness targets on shipyard data.
- Deploys and operates in the air-gapped environment with RBAC, audit and encryption.
- Provides an end-to-end auditable trail from determination to drawing incorporation.

### 10.4 Definition of Ready (a work item may start)

- Traces to a numbered FR/NFR or a logged commitment.
- Input data format and source identified and available.
- Acceptance test defined.
- Any SME dependency identified and SME availability confirmed.
- Any rule dependency: rule digitised and SME-signed-off.

### 10.5 Definition of Done (a work item is complete)

- Implemented, unit and integration tested, passing.
- Traceability matrix (§40) updated.
- Explainability output present — no engineering finding ships without evidence chain.
- Audit trail entries emitted for all state-changing actions.
- Works with zero outbound network access.
- Documented in user or admin manual as applicable.
- Regression fixtures added where a rule or algorithm changed.

### 10.6 KPI categories

| Category | KPIs |
|---|---|
| Business | K3, K4, K5 — man-hour reduction, rework reduction, BOM error reduction |
| Operational | K6, PT-10, PT-11, PT-12 — response and throughput |
| Technical | PT-01, PT-02, PT-09 — accuracy and graph completeness |
| Quality | K1, K2, PT-03, PT-04, PT-08 — agreement, citation correctness, false negatives, explainability coverage |
| Security | Air-gap verification pass, RBAC enforcement verification, encryption verification, zero outbound connections |
| Compliance | K7, PT-08 — 100% audit trail, 100% traceability |

### 10.7 Bid evaluation rubric (MDL, Annexure-II §15)

Relevant to bid outcome, not to delivery. Recorded because it explains which sections of the submission carry weight.

| Criterion | Max |
|---|---|
| 1. Relevant Experience (evidenced AI/GenAI projects 8; domain relevance 7; secure/air-gapped deployment experience 5) | 20 |
| 2. Understanding of Problem Statement (problem articulation & edge cases 6; clarification questions, assumptions, dependencies 4) | 10 |
| 3. Solution Architecture (completeness 6; data-flow clarity 4; CAD/PLM integration & as-fitted hand-off 3; scalability 2) | 15 |
| 4. AI/GenAI Technical Capability (appropriateness of CV/3D/OCR/RAG/LLM choices 6; remainder unspecified in source) | 15 |
| 5. Similar Project Experience (drawing interpretation / CV inspection / deviation / as-built vs as-designed) | 15 |
| 6. Security & Air-Gapped Readiness | 10 |
| 7. Product Maturity / Feature Compliance | 10 |
| 8. Team Capability | 5 |
| **Total** | **100** |

Every claim must be evidenced; unevidenced claims score at the lowest band. Criteria 1, 5 and 7 total 45 points and are where a Research-maturity bidder with one demonstrable prior project is structurally weakest.

---

## 11. Assumptions, Constraints & Dependencies

### 11.1 Assumptions

| ID | Assumption | Owner | If false |
|---|---|---|---|
| A-01 | Relevant CAD models, BOMs, engineering documents and revision histories will be made available for integration | MDL | Pilot cannot proceed; schedule slips |
| A-02 | Applicable classification rules and standards can be provided or referenced by MDL (licensed copies) | MDL | Compliance engine has no content; core value blocked |
| A-03 | SMEs will be available for validation of engineering dependencies, rules and business logic | MDL | Rule activation blocked (SME sign-off is mandatory); graph quality degrades |
| A-04 | Necessary IT infrastructure available within MDL's secure environment per agreed hardware spec | MDL | Deployment blocked |
| A-05 | Required approvals available for access to engineering and configuration data | MDL | Blocked |
| A-06 | Representative historical data exists in sufficient volume for ML training (target ≥500 matched CAD-BOM pairs, ≥100 known mismatches per discrepancy type) | MDL | System runs deterministic-only; ML confidence scoring deferred. **Mitigated by design** — cold-start mode exists |
| A-07 | MDL's CAD formats fall within OCC-supported formats or bridgeable equivalents | MDL / Phase 0 | Fallback bridges required; possible scope addition |
| A-08 | Tolerances, thresholds, severity levels and acceptance limits will be agreed jointly during pilot | Joint | Cannot calibrate; false positive rate unmanaged |

### 11.2 Constraints

| ID | Constraint | Source |
|---|---|---|
| C-01 | Must operate within a secure, on-premise / air-gapped environment | SoW §13 |
| C-02 | Must comply with GoI procurement restrictions on land-border countries and with CERT-In cybersecurity guidelines | SoW §13, NFR-02 |
| C-03 | All data remains within shipyard infrastructure; licensed class-rule content must be protected and not redistributed | SoW §13, NFR-03 |
| C-04 | 12-month delivery window | Revised project plan |
| C-05 | Final engineering, certification and production release authority remains with MDL at all times | Scope boundary |
| C-06 | Compliance-critical paths must be deterministic and reproducible — no ML in the determination path | NFR-04, architecture principle AP-01 |
| C-07 | No online or autonomous learning in production | MLOps policy |
| C-08 | Enterprise full-ship-scale hardware is outside the current PS-71 hardware budget band | Hardware spec §11 |

### 11.3 Dependencies

| ID | Dependency | Type | Criticality |
|---|---|---|---|
| DEP-01 | Machine-readable design parameters, BOM and 3D models | MDL data | Blocking |
| DEP-02 | Licensed class-rule / standards / regulation documents | MDL data | Blocking |
| DEP-03 | PLM / ERP / CAD access as required | MDL systems | Blocking for Phase 2 integration |
| DEP-04 | Shipyard compute/GPU infrastructure per agreed spec | MDL infrastructure | Blocking for Phase 3 |
| DEP-05 | SME time for rule validation and dependency seeding | MDL people | Blocking for rule activation |
| DEP-06 | MDL participation in pilot validation and UAT | MDL people | Blocking for acceptance |
| DEP-07 | Phase 0 integration assessment completed before Phase 2 adapter work | Internal sequencing | Blocking |
| DEP-08 | Baseline compliance scan recorded per component before delta mode can operate | Internal sequencing | Blocking for F-CMP-06 |

### 11.4 Clarification questions outstanding with MDL

1. Which CAD platforms and versions are currently used across MDL projects?
2. What level of BOM maturity and standardisation exists across programmes?
3. Which classification societies and defence standards are applicable for the target projects?
4. What existing configuration management and engineering change processes are followed?
5. What level of integration is expected with existing PLM, ERP, CAD and document management systems?

---

## 12. Risks & Mitigation

### 12.1 Risk register

Severity = impact × likelihood at current state.

| ID | Risk | Severity | Mitigation | Owner |
|---|---|---|---|---|
| **R-01** | **Maturity gap.** Product is Research-stage with zero code, yet 12 Functional Compliance Matrix rows are committed as working at MVP inside a 6-month Phase 1 | **Critical** | Ruthless Phase 1 sequencing: deterministic core only, no ML, no GenAI, minimum viable rule subset. Phase 0 must produce a working demo of one clause-cited compliance check *or* one CAD–BOM mismatch — that is the entire Phase 0 acceptance bar and it is achievable. Re-plan Phase 1 against the 12 committed rows explicitly and identify which are at risk before kickoff | Delivery lead |
| **R-02** | **Rule digitisation complexity.** Class rules are dense semi-structured prose; incomplete extraction causes false compliance passes — which is the failure mode PT-04 forbids | **Critical** | Template-based parsing with SME validation loops; scope limited to high-impact rules (structural, material, load cases); Phase 1 target top ~30% critical rules by severity and frequency; mandatory SME sign-off before any rule activates; known-good/known-bad test fixtures per rule | Rule/domain lead |
| **R-03** | **Graph construction quality.** Incomplete BOM-to-dependency mapping produces false negatives in impact analysis — silent, and therefore worse than a visible error | **High** | Phase 0 constraint catalogue; SME-reviewed seed templates; ≥95% coverage gate before go-live; isolated-node flagging surfaced on the dashboard; edge-weight calibration via SME workshop | Architecture lead |
| **R-04** | **CAD format fragmentation.** MDL may use custom or legacy formats OCC does not support natively | **High** | OCC supports 8+ formats; Phase 0 format assessment is a gate; LibreCAD / SolidWorks API bridges as fallback; format risk quantified before Phase 1 commits | Integration lead |
| **R-05** | **PLM/ERP integration complexity.** MDL's environment may differ substantially from standard adapter assumptions | **High** | Phase 0 integration assessment collects actual interface specs; adapter customisation scope agreed *before* Phase 3 integration work begins; file-system fallback paths designed for every connector | Integration lead |
| **R-06** | **Classification rule freshness.** Rules are updated periodically; stale rules cause false compliance passes | **High** | Structured catalog with `effective_date`; quarterly update process documented in the FOM; IRS/DNV/BV rule feeds monitored; PKI-signed offline update packages | Rule/domain lead |
| **R-07** | **Air-gap update friction.** On-premise deployment complicates model retraining and software updates | Medium | Containerised deployment with offline update packages; retraining pipeline included in handover documentation; all artefacts version-controlled in object storage | DevOps lead |
| **R-08** | **Training data unavailability.** Insufficient historical labelled data for ML confidence scoring | Medium | **Already mitigated architecturally** — deterministic cold-start mode delivers full sync functionality with no training data. ML activates in Phase 2 only if data materialises | ML lead |
| **R-09** | **12-month compression.** Plan was originally 20 months; the same scope now has 40% less time | **High** | GenAI layer explicitly de-scoped to non-core and deferrable (§22.13). Phase 6 production-enhancement content must be either absorbed or formally dropped. **Action: the 20→12 month re-plan has not actually been done at task level — only the headline changed.** See AI-01 | Delivery lead |
| **R-10** | **Disclosed-but-unused components.** YOLOv11, SAM 2, Open3D, PDAL, VTK are in the security-clearance disclosure but no committed feature uses them | Medium | Resolve with the §6.4 conditional-scope decision. If as-installed is declined, remove from disclosure. Carrying unused AGPL-v3 (YOLOv11) in a defence disclosure is an unnecessary licence exposure | Security/compliance lead |
| **R-11** | **T2 interpretation risk.** MDL's Task 2 says "incorporate the changes in detail design in the 3D model"; AURORA does not write geometry back | **High** | Confirm interpretation with MDL before Phase 1 scope freeze. If write-back is expected, this is a significant architectural addition. See OQ-03 | Delivery lead |
| **R-12** | **SME availability.** Rule activation, graph seeding and validation all gate on MDL SME time, which is outside our control | **High** | Front-load SME asks into Phase 0/1; batch SME reviews; make SME dependency visible in every gate review so unavailability is MDL's tracked risk, not a silent slip | Delivery lead |
| **R-13** | **Multi-society conflict resolution policy.** Applying "the more conservative value" automatically is an engineering judgement encoded as a default | Medium | Every conflict raises `MULTI_SOCIETY_CONFLICT` for review; the conservative default is never silent. Confirm policy acceptability with MDL in Phase 1 | Rule/domain lead |
| **R-14** | **Licensed rule content handling.** Class rule books are licensed; ingesting them into a searchable knowledge base may have licensing implications | Medium | Confirm licensing terms per society with MDL; access-controlled storage; no redistribution; no export of rule text in reports beyond citation references | Legal / compliance |

### 12.2 Risk posture summary

The technical architecture is sound and the risks that remain are overwhelmingly **execution and data-dependency** risks, not design risks. The two that could sink the programme are **R-01** (maturity vs MVP commitment) and **R-02** (rule digitisation quality, because it directly threatens the PT-04 zero-false-negative claim). Both are addressable but neither is addressed by anything currently written down — they need a real Phase 1 plan, not a mitigation sentence.

---

## 13. System Architecture

### 13.1 Architecture principles

| ID | Principle | Implication |
|---|---|---|
| AP-01 | **Deterministic-first.** Compliance-critical workflows are rule-based, reproducible and auditable | ML never appears in a compliance determination path. Identical inputs always yield identical outputs |
| AP-02 | **Evidence or silence.** No engineering output without a traceable evidence chain | Every finding carries clause, values, inputs, steps, confidence, version |
| AP-03 | **Human authority is architectural, not procedural.** | No code path reaches production release without an authorised human approval. Overrides require justification text |
| AP-04 | **Air-gap native.** Offline is the design target, not a deployment option | Zero outbound calls anywhere in the stack, including telemetry |
| AP-05 | **Layer isolation.** Every layer has well-defined interfaces | Independent module validation; incremental integration; phased deployment |
| AP-06 | **Graceful degradation.** Optional capability failing must not degrade core capability | No GPU → optimisation and surrogate models disable, core unaffected. No training data → deterministic matching. No PLM → file-system fallback |
| AP-07 | **Integrate, don't replace.** AURORA is a layer above existing systems | Standards-based interchange; no vendor lock-in; existing manual process remains the fallback |
| AP-08 | **Change-scoped, not full-scan.** Validation follows the change, not the calendar | Delta compliance mode; targeted re-validation; graph-scoped traversal |

### 13.2 Layered architecture

| Layer | Name | Components & responsibility |
|---|---|---|
| **L1** | Input | Multi-format CAD ingestion via OCC (STEP, IGES, JT, CATIA V5/V6, NX, SolidWorks); BOM ingestion (CSV/XML/XLSX); classification rule catalog loader; 2D drawing ingestion (PDF/TIFF/DWG/DXF) with OCR; FEA/CFD simulation result ingestion; REST ingestion API; JSON schema validator |
| **L2** | Digital Twin / Unified Component Registry | Parametric component model — `component_id`, geometry features, material properties, mass properties, BOM entry, rule bindings, simulation refs, version history. Persisted in PostgreSQL + object storage |
| **L3** | Graph | ArcadeDB dependency knowledge graph; weighted BFS impact propagation engine; edge weight configuration |
| **L4** | Design Intelligence | Multi-society rule compliance engine (Drools); CAD–BOM synchronisation engine (multi-signal + ML confidence); NSGA-II design optimisation |
| **L5** | Drawing Sync | Drawing format parsing (DXF/PDF); title block update; revision cloud generation; PLM drawing vault integration; drawing–CAD mismatch detection |
| **L6** | Integration | REST API gateway; CAD system connectors; ERP connector; PLM adapter stubs; async task queue |
| **L7** | Output | Decision Intelligence Dashboard (React + TypeScript, on-premise); PDF report generator; audit trail database |
| **L8*** | GenAI *(non-core)* | Local LLM, RAG pipeline, vector index, natural-language query, rule interpretation, narrative report generation. **Sits above L7. Optional. Deferrable. Never in a determination path.** |

All layers are co-located within a single on-premise deployment over a shared Digital Twin Core and Dependency Knowledge Graph.

### 13.3 Component responsibilities

| Component | Responsibility | Depends on |
|---|---|---|
| CAD Parsing & Normalisation Engine | Format detection/conversion, shape healing, assembly decomposition, geometric property computation, topology hashing | OCC / PythonOCC |
| Unified Component Registry | Single component identity spanning CAD, BOM, rules, simulation, drawings, versions | PostgreSQL, object store |
| Dependency Knowledge Graph Engine | Encode and serve all inter-system dependency relationships | ArcadeDB, CAD parser, BOM ingestion, SME dependency matrix |
| Impact Propagation Engine | Weighted BFS traversal producing ranked impact with propagation paths | Knowledge graph |
| CAD–BOM Synchronisation Engine | Multi-signal correspondence resolution and discrepancy classification | CAD parser, BOM ingestion, ML confidence model |
| Multi-Society Rule Compliance Engine | Deterministic rule evaluation, clause citation, conflict detection, delta mode | Drools, rule catalog, registry, simulation refs |
| Design Optimisation Engine | Multi-objective trade-off exploration, Pareto output, sensitivity analysis | pymoo/NSGA-II, registry, compliance engine |
| Drawing Synchronisation & Revision Engine | Drawing staleness detection, title block/revision cloud update, production release queue | ezdxf, PDF tooling, PLM adapter |
| Classification Submission Module | Package assembly, society query ingestion, re-submission readiness | Compliance engine, drawing engine, graph |
| Decision Intelligence Dashboard | Unified engineer-facing interface across all engine outputs | All engines, REST API |
| Integration Layer | REST gateway, connectors, async job orchestration | All engines |
| Audit & Governance Service | Immutable hash-chained logging of all actions and decisions | PostgreSQL |
| GenAI Assistant *(non-core)* | NL query, rule interpretation, narrative generation — strictly over deterministic outputs | Local LLM, vector index, all engines |

### 13.4 Data flow (end to end)

```
CAD files ──┐
BOM data ───┤
Drawings ───┼──► L1 Ingestion ──► normalise, heal, hash, extract ──► L2 Unified Component Registry
Rules ──────┤                                                              │
Sim results ┘                                                              ▼
                                                          L3 Dependency Knowledge Graph
                                                                           │
              ┌────────────────────────────┬─────────────────────────────┬─┘
              ▼                            ▼                             ▼
   CAD–BOM Sync Engine          Compliance Engine (Drools)     Impact Propagation Engine
              │                            │                             │
              └────────────┬───────────────┴──────────────┬──────────────┘
                           ▼                              ▼
                 Optimisation Engine            Drawing Sync & Revision Engine
                           │                              │
                           └──────────────┬───────────────┘
                                          ▼
                        Human review & approval checkpoint (mandatory)
                                          ▼
              ┌───────────────────────────┼───────────────────────────┐
              ▼                           ▼                           ▼
      Dashboard / Reports      Classification Submission     Production Release Queue
              │                           │                           │
              └───────────────────────────┴───────────────────────────┘
                                          ▼
                          Immutable hash-chained Audit Trail
```

---

## 14. Technology Stack

### 14.1 Baselined decisions

These supersede any conflicting statement in the bid documents. See §42 for what they supersede.

| Area | Decision | Rationale |
|---|---|---|
| Graph database | **ArcadeDB** | Broader feature set than Neo4j; multi-model; Apache 2.0; Italy-origin (satisfies NFR-02); matches the §8.2 security-clearance disclosure |
| Deterministic rule engine | **Drools** | Mature production rule engine; rule authoring decoupled from application code, which is what NFR-09 and NFR-10 require; matches §8.2 disclosure |
| ML libraries | **XGBoost / LightGBM, Scikit-learn, PyTorch — all retained** | Selection is empirical, per task, on validation performance during Phase 2. No single-library lock-in |
| GenAI layer | **Non-core, low priority, deferrable** | Entered scope in the final bid draft; no mandatory requirement depends on it |
| Project duration | **12 months** | Revised down from the original 20-month plan |

### 14.2 Full stack (as disclosed to MDL, Annexure-II §8.1)

| Layer | Technology | Version | Licence | Origin |
|---|---|---|---|---|
| Language | Python | 3.12 LTS | PSF | Netherlands |
| Language | TypeScript | 5.8 | Apache 2.0 | USA |
| Frontend | React | 19 | MIT | USA |
| Backend | FastAPI | 0.116+ | MIT | USA |
| Backend | Uvicorn | 0.35 | BSD | USA |
| Backend | SQLAlchemy | 2.0 | MIT | USA |
| Backend | Alembic | 1.16 | MIT | USA |
| Backend | Pydantic | 2.11 | MIT | USA |
| ML | PyTorch | 2.7 | BSD | USA |
| ML | Scikit-learn | 1.7 | BSD | France |
| CV | OpenCV | 4.12 | Apache 2.0 | USA |
| CV | Segment Anything 2 (SAM 2) | LTS | Apache 2.0 | USA |
| CV | YOLOv11 | LTS | **AGPL-v3** | USA |
| 3D / Point Cloud | Open3D / PDAL / VTK | 0.19 / 2.9 / 9.x | MIT / BSD / BSD | USA |
| OCR | Tesseract OCR | 5.5 | Apache 2.0 | USA |
| LLM | Llama 3.1 8B Instruct (offline) | latest | Meta Community Licence | USA |
| Embeddings | all-mpnet-base-v2 (Sentence Transformers) | v2 | Apache 2.0 | UK |
| Vector DB | Qdrant | 1.15 | Apache 2.0 | Poland |
| Knowledge Graph | **ArcadeDB** | 25.x | Apache 2.0 | Italy |
| Primary DB | PostgreSQL | 17 | PostgreSQL Licence | USA |
| Cache / Queue | Redis | 8 | RSALv2 / SSPLv1 | USA |
| Rule Engine | **Drools** | 10.x | Apache 2.0 | USA |
| NLP | spaCy | 3.8 | MIT | Germany |
| ML tooling | Hugging Face Transformers | 4.53 | Apache 2.0 | USA |
| Inference | ONNX Runtime | 1.22 | MIT | USA |
| Containers | Docker Engine | 28 | Apache 2.0 | USA |
| Orchestration | Kubernetes | 1.33 | Apache 2.0 | USA |
| OS | Ubuntu Server LTS | 24.04 | GPL | UK |

Additional components referenced in the solution design: OpenCascade Technology / PythonOCC (CAD kernel), pymoo (NSGA-II), ezdxf (DXF manipulation), reportlab / pypdf (PDF), Celery (task queue), MinIO (S3-compatible object storage), Nginx (static serving), SHAP (explainability).

> **Internal note.** Two items need attention. (1) **YOLOv11 is AGPL-v3** — the only copyleft component in the stack, and it is currently attached to no committed feature. If as-installed scope is declined (§6.4), remove it. (2) **Redis 8 is RSALv2/SSPLv1**, not open source in the OSI sense; Valkey (BSD-3) is the identified drop-in alternative and may be the safer choice for a defence procurement.

### 14.3 Declared alternatives (supply-chain resilience)

Disclosed to MDL so that no single component is a lock-in point.

| Component | Alternatives |
|---|---|
| Python | C++20, Rust |
| TypeScript | Java 21, Kotlin |
| React | Angular, Vue.js |
| FastAPI | ASP.NET Core, Spring Boot |
| Uvicorn | Hypercorn, Gunicorn |
| SQLAlchemy | Prisma, Hibernate |
| Alembic | Flyway, Liquibase |
| Pydantic | attrs, Marshmallow |
| PyTorch | TensorFlow, JAX |
| Scikit-learn | XGBoost, CatBoost |
| OpenCV | OpenVINO, HALCON (commercial) |
| Open3D | PCL, PDAL, VTK |
| YOLOv11 | RT-DETR, Faster R-CNN, DETR |
| SAM 2 | Mask R-CNN, YOLOv11 Segmentation |
| Tesseract | EasyOCR, Azure Read OCR (commercial) |
| HF Transformers | vLLM, llama.cpp |
| Sentence Transformers | FlagEmbedding, Instructor Embeddings |
| all-mpnet-base-v2 | e5-large-v2, bge-large-en-v1.5 |
| spaCy | Stanza, NLTK |
| ONNX Runtime | OpenVINO Runtime, TensorRT |
| Llama 3.1 8B | Mistral 7B, Phi-4, Gemma 3 |
| Qdrant | FAISS, ChromaDB, Weaviate |
| ArcadeDB | Neo4j Community, JanusGraph, RDF4J |
| PostgreSQL | MariaDB, MS SQL Server |
| Redis | **Valkey (BSD-3)**, RabbitMQ |
| Drools | OpenL Tablets, Easy Rules |
| Docker | Podman |
| Kubernetes | K3s, OpenShift (commercial) |

### 14.4 Country-of-origin summary (NFR-02 compliance)

USA, UK, France, Germany, Italy, Poland, Netherlands. **No component originates in, routes to, is stored in, is processed by, or is controlled from any country sharing a land border with India.** Compliant with the Order (Public Procurement No. 1), Department of Expenditure, Ministry of Finance.

---

## 15. Infrastructure, Deployment & Environments

### 15.1 Deployment architecture

- Fully containerised. **Docker-Compose** for the standard tier; **Kubernetes** manifests for the enterprise tier.
- All services co-located on-premise. No external network required post-deployment.
- FastAPI + Uvicorn (ASGI) backend; React frontend built as a static bundle served from Nginx on-premise.
- Async task queue (Celery + Redis) for all long-running jobs: CAD parsing, optimisation, ML inference. Status polled via REST.
- Object storage (MinIO, S3-compatible, telemetry disabled) for CAD files, simulation results and versioned model artefacts.

### 15.2 Air-gap deployment package

| Element | Detail |
|---|---|
| Container images | Exported as `.tar` archives via `docker save`, loaded on-premise via `docker load`. No registry access required post-delivery |
| Private registry | Docker Registry v2 (containerised) bundled for Kubernetes environments |
| Third-party services | Redis 7.x/8 containerised with no external connections; MinIO with `MINIO_UPDATE=off` and all telemetry disabled, no AWS S3 endpoint calls; PostgreSQL containerised |
| Dependencies | All Python/JS packages, models and libraries pre-bundled offline |
| Updates | Signed offline update packages; cryptographic integrity verification before installation |
| Rule updates | PKI-signed offline rule catalog packages, validated before install |
| Documentation | Deployment, recovery and operational maintenance runbooks included |

### 15.3 Environment configuration

| Environment | Purpose | Configuration |
|---|---|---|
| Dev | Arcaisys-side development | Single workstation tier, containerised, synthetic/sample data |
| Test | Integration and regression | Mirrors recommended tier where possible |
| Pilot | MDL-side Phase 1 pilot | Recommended tier, MDL representative data, runs alongside existing manual process |
| Production | Phase 3 air-gapped deployment | Recommended tier minimum; enterprise tier for full-ship scale |

> **Not yet defined.** Per-environment variable schema, secrets management approach, and config-as-code layout. **Trigger:** Phase 1 development start.

### 15.4 Hardware specification (as disclosed)

| Resource | Minimum (Dev/Test workstation) | Recommended (~10,000-node scale) | Enterprise (full-ship, future) |
|---|---|---|---|
| CPU | 8-core (i7 / Ryzen 7), 32 GB RAM | Dual Xeon Silver 4310 (24 cores) or EPYC 7313, 128 GB RAM per node × 2 nodes | Dual Xeon Gold / EPYC 64+ cores, 256 GB+ RAM, clustered × 4–6 nodes |
| GPU | RTX 3060 12 GB (CAD viz only, no ML training) | RTX 3090 or equivalent 24 GB VRAM × 1–2; CPU-only inference fallback | RTX A6000 / A100 40–80 GB × 2–4, clustered for multi-ship-class retraining |
| RAM | 32 GB | 128 GB per node (256 GB aggregate) | 512 GB – 1 TB aggregate |
| Storage | 1 TB NVMe SSD local | 4 TB NVMe hot (DB/graph) + 20 TB RAID6 NAS/object store | 10 TB+ NVMe hot + 100 TB+ scalable object storage, replicated |
| OS | Ubuntu Desktop LTS 22.04/24.04 | Ubuntu Server LTS 24.04, Docker-Compose | Ubuntu Server LTS 24.04 / RHEL, Kubernetes HA cluster |
| Database | PostgreSQL single instance | PostgreSQL + ArcadeDB + Redis + MinIO, all containerised | PostgreSQL HA/replicated + ArcadeDB clustered + Redis Sentinel + MinIO distributed |
| Network & security | Standard LAN, local firewall | Managed switch, air-gap boundary/firewall appliance, mTLS between microservices | Zero-trust fabric, redundant switching, IDS/IPS, SOC integration |
| Specialised | Not required | 10 KVA online UPS; backup/tape unit for offline update packages; biometric/smart-card RBAC reader (optional) | N+1 UPS redundancy; automated offline patch-delivery appliance; edge scanning stations at drawing office |

**GPU is optional.** Without a GPU, the PyTorch surrogate module disables and the system runs fully deterministic with no degradation to compliance validation, CAD–BOM sync, dependency analysis or drawing management.

### 15.5 Network architecture

- **Air-gapped.** No inbound or outbound internet connectivity at install-time or run-time.
- Air-gap boundary / firewall appliance at the deployment perimeter.
- mTLS between microservices (recommended tier and above); zero-trust segmentation at enterprise tier.
- TLS 1.3 for all user, service, database and API traffic, with customer-managed certificates.
- Authentication against on-premise LDAP / Active Directory.

> **Not yet defined.** Port map, service mesh topology, VLAN/subnet allocation. **Trigger:** Phase 0 network topology review with MDL IT.

---

## 16. Data Architecture

### 16.1 Data sources

| Source | Type | Owner | Format |
|---|---|---|---|
| 3D CAD models | Design geometry | MDL Design | STEP, IGES, IFC, JT, CATIA V5/V6, NX, SolidWorks |
| Detail design parameters | Design data | MDL Design | CAD attributes, PLM records, spreadsheets |
| Bill of Material | Configuration | MDL ERP/PLM | CSV, XML, XLSX, ERP extract |
| 2D drawings | Documentation | MDL Drawing Office | PDF, TIFF, DWG, DXF |
| Class rules / standards / regulations | Reference | MDL (licensed) | PDF, scanned PDF, structured text |
| FEA/CFD simulation results | Analysis | MDL Engineering | Solver output + result summaries |
| Discipline dependency information | Domain knowledge | MDL SMEs | SME-maintained dependency matrix |
| Tolerances / thresholds | Configuration | MDL + joint agreement | Configuration data |
| Society queries | External | Classification societies | Structured JSON (post-ingestion) |

### 16.2 Ingestion pipeline

```
Raw input
   ▼
Format detection ──► unsupported? ──► fallback bridge / flag
   ▼
Conversion to internal representation (BREP for 3D)
   ▼
Shape healing (degenerate faces, gaps, orientation)
   ▼
Assembly decomposition (XCAF tree traversal, component_id assignment)
   ▼
Geometric property computation (volume, area, bbox, centroid, CoM, inertia)
   ▼
Topology hashing (SHA-256 over sorted {face_area, edge_length, vertex_coords})
   ▼
Metadata extraction / OCR (drawings, rules)
   ▼
Validation (missing attributes, conflicts, duplicates, unresolved refs)
   ▼
Unified Component Registry + graph edge seeding
```

Incomplete input does not halt ingestion. The system continues on validated data and explicitly flags missing dependencies, unresolved references and confidence limitations.

### 16.3 Storage architecture

| Store | Technology | Contents |
|---|---|---|
| Relational | PostgreSQL 17 | Unified Component Registry, audit trail, workflow state, rule catalog metadata, users/roles |
| Graph | ArcadeDB | Dependency knowledge graph — nodes, edges, weights |
| Object | MinIO (S3-compatible) | CAD files, simulation results, ML model artefacts, generated reports, drawing files |
| Vector *(non-core)* | Qdrant | Document embeddings for the GenAI/RAG layer |
| Cache / broker | Redis | Celery task queue, session cache |
| Version control | Local Git (inside air-gap) | Engineering artefacts, baselines, tags |

### 16.4 Core data model — Digital Twin node schema

Every physical ship component is one node with this structure:

| Field | Type | Contents |
|---|---|---|
| `component_id` | UUID | Globally unique. **The join key** linking CAD assembly path to BOM part number |
| `geometry_features` | object | `bounding_box`, `surface_area`, `volume`, `centroid`, `moments_of_inertia`, `topology_hash` |
| `material` | object | `material_code`, `grade`, `density`, `yield_strength`, `UTS`, `thermal_conductivity`, `corrosion_class` |
| `mass_properties` | object | `mass_kg`, `cog_xyz`, `inertia_tensor` |
| `bom_entry` | object | `part_number`, `description`, `quantity`, `unit_cost`, `supplier_code`, `lead_time_days` |
| `rule_bindings` | array | `[{rule_id, class_society, parameter_name, limit_value, limit_type}]` |
| `simulation_refs` | array | `[{sim_type, sim_file_path, result_summary, pass_fail, timestamp}]` |
| `version_history` | array | `[{timestamp, changed_by, change_description, delta_hash}]` |

### 16.5 Rule catalog schema

| Field | Contents |
|---|---|
| `rule_id` | Unique identifier, e.g. `IRS-2024-STRUCT-3.2.1` |
| `class_society` | `IRS` \| `LLOYDS` \| `DNV` \| `BV` \| `ABS` \| `ISO` \| `IACS` \| `MIL-SPEC` |
| `rule_type` | `dimensional_limit` \| `material_requirement` \| `process_requirement` \| `arrangement_requirement` \| `load_case` \| `environmental_condition` |
| `severity` | `CRITICAL` \| `MAJOR` \| `MINOR` \| `ADVISORY` |
| `effective_date` | Applicability date. Superseded rules retained for historical compliance checks |
| `conditional_expression` | Determines rule applicability against component attributes; also drives delta-mode rule selection |
| `limit_value` / `limit_type` | The threshold and its comparison semantics |
| `source_reference` | Document, clause and revision — the citation shown to the user |
| `sme_signoff` | Approver, date. **Rule does not activate without this** |

### 16.6 Graph data model

**Nodes:** components (from BOM line items and CAD assembly nodes), with attributes `part_number`, `system`, `material`, `location`, `unit_cost`, `lead_time`. Rules are also represented as nodes for `RULE_GOVERNS` edges.

**Edge taxonomy:**

| Edge type | Physical meaning | Weight basis |
|---|---|---|
| `ASSEMBLY_CHILD` | CAD assembly hierarchy | Structural (auto-populated from CAD) |
| `STRUCTURALLY_SUPPORTS` | A bears load of B | Load-sharing ratio |
| `ELECTRICALLY_FEEDS` | Power or signal dependency | Voltage/current dependency ratio |
| `THERMALLY_ADJACENT` | Thermal influence between co-located components | Spatial proximity factor |
| `ROUTED_THROUGH` | Cable or pipe routed through a structural element | Contact area ratio |
| `MECHANICALLY_CONNECTED` | Direct mechanical fastening or joint | Contact area / joint stiffness |
| `PHYSICAL_INTERFACE` | Physical contact between components | Contact area (from OCC interference detection) |
| `FUNCTIONAL_DEPENDENCY` | Functional coupling | SME dependency matrix |
| `RULE_GOVERNS` | Classification rule applicable to a component | Rule criticality weight |

**Construction pipeline:** BOM ingested → nodes created. `ASSEMBLY_CHILD` auto-populated from CAD hierarchy (no manual input). `PHYSICAL_INTERFACE` derived from bounding-box intersection plus gap analysis confirming contact. `FUNCTIONAL_DEPENDENCY` and `RULE_GOVERNS` populated from rule catalog and SME dependency matrix. Completeness validated: isolated nodes flagged; **≥95% of BOM items with ≥1 edge is a go-live gate**.

### 16.7 Data relationships (traceability chain)

```
Design parameter ─► Rule (clause) ─► Compliance finding
       │                  ▲                  │
       ▼                  │                  ▼
   Component ◄──── rule_bindings        Disposition
    (UUID)                                   │
    │   │                                    ▼
    │   └──► BOM item ──► Procurement    Approval
    │                                        │
    └──► CAD assembly node                   ▼
             │                        Drawing revision
             └──► Drawing ────────────────────┘
                        │
                        ▼
              Production release package
```

Every link in this chain is queryable in both directions. This is what satisfies FR-15 and NFR-12.

### 16.8 Data lifecycle & retention

| Stage | Behaviour |
|---|---|
| Ingest | Validated, normalised, hashed, registered |
| Active | Live in registry and graph; participates in analysis |
| Revised | Prior version retained in `version_history`; delta hash recorded |
| Baselined | Immutable snapshot tagged (Contract Design / Basic Design / Class Submission / Class Approved / Production Release) |
| Superseded | Retained and accessible for audit, comparison and rollback — **never deleted** |
| Archived | Securely archived, remains fully accessible for audit and regulatory compliance |

Superseded rule versions are retained indefinitely so that a past compliance determination can always be re-derived against the rules in force at the time.

> **Not yet defined.** Concrete retention periods per data class. **Trigger:** MDL data governance policy input, Phase 0.

### 16.9 Data validation & quality rules

**At ingestion:** missing attributes, conflicting information, duplicate records, unsupported formats, inconsistent engineering references.

**Continuous quality gates:**

| Gate | Threshold | Consequence if failed |
|---|---|---|
| Graph completeness | ≥95% BOM items with ≥1 edge | Go-live blocked |
| Isolated nodes | Flagged individually | SME review required |
| Rule activation | SME sign-off present | Rule does not activate |
| CAD–BOM match confidence | <0.6 | Routed to manual review |
| CAD–BOM match confidence | ≥0.85 | Auto-confirmed |
| Compliance finding confidence | Below threshold | Routed to engineer review |
| Data freshness | Per-source staleness | Dashboard alert |

**Governing principle:** the system never makes an unverified engineering decision automatically. Low-confidence scenarios escalate to authorised users.

### 16.10 Data handling policy

All data is classified and retained within shipyard infrastructure. No external transmission of any kind. Licensed rule content is handled per licensing terms, access-controlled, and never redistributed. No production data leaves the MDL environment — including for model training, which occurs entirely on-premise.

---
## 17. APIs & External Integrations

### 17.1 API architecture

All engine interactions are orchestrated by a FastAPI + Uvicorn async backend exposing a REST API gateway. Full **OpenAPI 3.0** specification is a deliverable (D-05). Long-running jobs are dispatched to Celery and polled via REST rather than held on a synchronous connection.

### 17.2 Integration targets

| Target | Protocol | Data exchanged | Notes |
|---|---|---|---|
| PLM (Teamcenter, Windchill, ENOVIA) | REST adapter stubs | BOM, drawing metadata, revision history, approval status | Stubs provided; full integration activated on client environment access |
| ERP (SAP PM, Oracle) | REST / OData | Cost rates, supplier data, BOM sync | ERP-side configuration required; bi-directional BOM sync |
| CAD (CATIA, NX, SolidWorks, AutoCAD) | File watcher / webhook | CAD models, assembly hierarchy, geometry hashes | On-save hooks trigger ingestion; webhook endpoint configurable per format |
| Async task queue (Celery + Redis) | Internal | Job status, engine outputs, error logs | All long-running jobs |
| Spreadsheet BOM import | File upload | BOM | Fallback where no direct ERP/PLM access exists |
| Drawing vault | PLM adapter | Drawing files, revision state | Fallback: file-system folder watch on a designated directory |

**Every connector has a documented non-integrated fallback.** This is deliberate — Phase 0 may reveal that MDL's environment does not support the assumed interface, and no core capability may depend on an integration that might not exist.

### 17.3 API contracts

> **Not yet defined.** Endpoint definitions, request/response schemas, error codes, versioning strategy, rate limiting. **Trigger:** Phase 1 (D3) — to be published as OpenAPI 3.0 under D-05 in Phase 2.

Known contract fixed points:
- Society query ingestion accepts `{query_id, rule_ref, component_id, query_text, response_due_date}` as structured JSON.
- Impact analysis output includes ranked component list with impact score and propagation path per entry.
- All engine outputs carry a confidence score and an evidence chain.

### 17.4 Integration protocols

REST/JSON as the default. OData for ERP where the ERP exposes it. Webhooks for CAD on-save events. File-system watch as universal fallback. Standards-based file interchange (STEP/ISO 10303, IGES, JT) for geometry to avoid proprietary lock-in per NFR-11.

---

## 18. Security Architecture

### 18.1 Authentication

| Mode | Status |
|---|---|
| Local user authentication | Supported |
| Microsoft Active Directory | Supported |
| LDAP | Supported |
| Enterprise SSO | Supported |
| JWT tokens for API session management | Supported |

Configurable per MDL infrastructure requirements. Session management via on-premise LDAP/AD.

### 18.2 Authorization & RBAC

| Role | Permissions |
|---|---|
| **Viewer** (Programme Manager / Observer) | Read-only: all panels, impact reports, audit trail. No actions |
| **Analyst** (Design / Systems Engineer) | All Viewer permissions + submit change requests, trigger all engine analyses, flag discrepancies |
| **Approver** (Lead Engineer / Programme Director) | All Analyst permissions + approve/reject drawings and changes, sign change records with digital approval, manage re-submission packages |
| **Admin** (IT / System Administrator) | Full access + user management, RBAC configuration, rule catalog editing, audit trail administration |

Role assignments managed via on-premise LDAP/AD. The role-based interface hides unnecessary controls, reducing operator error and cognitive load. Final role definitions to be aligned with MDL operational and security requirements during deployment.

### 18.3 Threat model

| Threat | Vector | Control |
|---|---|---|
| Data exfiltration | Outbound network call from any component | Zero outbound connectivity; telemetry disabled at build; air-gap boundary appliance; full component country-of-origin disclosure |
| Supply chain compromise | Malicious dependency in the offline bundle | SBOM; declared alternatives per component; signed offline packages with integrity verification; all images built and exported under control |
| Unauthorised engineering approval | Privilege escalation or shared credentials | RBAC with four separated roles; AD/LDAP-backed identity; immutable audit trail; digital approval signature |
| Silent tampering with the audit record | Direct database modification | Hash-chained audit log with integrity indicator surfaced in the UI |
| Licensed rule content leakage | Report export containing rule text | Citation references only in exports; access-controlled rule storage; no redistribution |
| False compliance pass | Stale or incompletely digitised rules | `effective_date` versioning; SME sign-off gate; known-good/known-bad fixtures; quarterly refresh process |
| Model manipulation | Retraining on poisoned data | No online/autonomous learning; offline retraining only; independent validation, regression, bias assessment and engineering review before deployment |
| Sovereignty violation | Component controlled from a land-border country | Full origin disclosure; declared alternatives; procurement-order compliance confirmed |

> **Not yet defined.** Formal STRIDE/DREAD threat model document, attack tree, and pen-test scope. **Trigger:** Phase 2 security hardening (D5), before Phase 3 security testing (D6).

### 18.4 Security controls

| Control | Implementation |
|---|---|
| Encryption at rest | AES-256 via database-level encryption, disk-level encryption, encrypted storage volumes and OS security controls. Configurable per MDL policy |
| Encryption in transit | TLS 1.3 / HTTPS for all user, service, database, API and internal traffic, with customer-managed certificates |
| Network segmentation | mTLS between microservices; zero-trust fabric at enterprise tier |
| Audit logging | All user actions, engine outputs and approval decisions, hash-chained in PostgreSQL |
| Telemetry | None mandatory. Optional analytics fully disableable. No usage data transmitted outside the deployment |
| Access control | RBAC, four roles, AD/LDAP-backed |
| Content protection | Licensed class-rule content access-controlled, not redistributed |
| Update integrity | PKI-signed offline packages, validated before installation |

### 18.5 Privacy requirements

Consideration for the Digital Personal Data Protection (DPDP) Act, 2023 in handling of operational user and audit data within on-premise environments. The system holds engineering data, not personal data, apart from user identity and action attribution in the audit trail — which is retained deliberately for NFR-12 auditability.

### 18.6 Compliance requirements

| Framework | Relevance |
|---|---|
| Order (Public Procurement No. 1), Dept. of Expenditure, Ministry of Finance | Land-border country restriction — **confirmed compliant** |
| CERT-In Security Guidelines | Cybersecurity, logging, incident response, secure deployment |
| National Cyber Security Policy (India) | Operational security for restricted environments |
| STQC Guidelines | Secure government software deployment and QA practice |
| ISO/IEC 27001 | Information security management principles |
| NITI Aayog Responsible AI Principles | Explainable, accountable, human-supervised AI workflows |
| MeitY Responsible AI & Trusted AI Guidance | Transparency, traceability, controlled decision-support |
| IndiaAI Mission | Strategic alignment — indigenous, secure, scalable AI infrastructure |
| DPDP Act 2023 | Controlled handling of user and audit data |
| Zero-Trust Security Principles | Segmented authentication, controlled inter-service trust |

### 18.7 Audit requirements

- Complete audit trail of all user and system actions (FR-25).
- Immutable, hash-chained, with an integrity indicator visible in the UI.
- Filterable by user, date range, action type and component ID.
- Exportable for compliance documentation.
- **100% auditable trail from determination → disposition → approval → drawing incorporation** (K7, NFR-12).
- Every engineer override recorded with timestamp, user ID and mandatory justification text.

---

## 19. AI / ML Specification

### 19.1 Where AI is and is not used

This is the most important paragraph in this section. **AURORA is deterministic-first.** Compliance determinations — the outputs that carry engineering and regulatory consequence — are produced by a rule engine, not a model. ML is confined to pattern-detection and acceleration where it demonstrably beats a deterministic baseline, and every ML output is confidence-scored, explainable and subject to human review. GenAI never produces an engineering determination under any circumstance.

| Capability | Approach | Why |
|---|---|---|
| Compliance determination | **Deterministic rules (Drools)** | Reproducibility and citability are regulatory requirements. A model cannot cite a clause as its cause |
| CAD–BOM matching | **Multi-signal deterministic + ML confidence scoring** | Correspondence resolution is genuinely a pattern problem; but the deterministic path must work alone (cold start) |
| Impact propagation | **Deterministic graph traversal** | Explainable propagation paths are required; a learned model cannot show its path |
| Design optimisation | **NSGA-II evolutionary algorithm** | Multi-objective trade-off exploration; output is advisory, not determinative |
| FEA acceleration | **PyTorch surrogate (future)** | Post-pilot enhancement only, once simulation data volume justifies it |
| Rule interpretation, NL query, narrative reports | **LLM + RAG (non-core)** | Usability layer over deterministic outputs. Never in a determination path |

### 19.2 Model inventory

| # | Model / component | Purpose | Inputs | Outputs | Status |
|---|---|---|---|---|---|
| M-01 | Gradient-boosting classifier (XGBoost / LightGBM / Scikit-learn candidates) | CAD–BOM match confidence scoring | Multi-signal feature vector (see §19.3) | Match confidence 0.0–1.0 | Phase 2. Cold-start deterministic fallback exists |
| M-02 | NSGA-II (pymoo) | Multi-objective design optimisation | ≥3 bounded quantifiable design parameters; weight/cost/compliance objectives | Pareto front of non-dominated alternatives | Phase 2. Falls back to sensitivity analysis |
| M-03 | SHAP | Feature attribution for M-01 and parameter sensitivity | Model + feature vector | Per-feature contribution | Phase 2 |
| M-04 | Tesseract OCR 5.5 | Text extraction from scanned drawings and rule documents | Raster images / scanned PDF | Text + layout | Phase 1 |
| M-05 | Llama 3.1 8B Instruct (local) | Rule interpretation, NL query, narrative generation | Retrieved context only | Natural language, always cited | **Non-core**, Phase 3 |
| M-06 | all-mpnet-base-v2 | Document embedding for RAG | Document chunks | Vectors | **Non-core**, Phase 3 |
| M-07 | PyTorch surrogate | FEA acceleration | Simulation feature space | Predicted structural response | **Future enhancement**, post-pilot |
| M-08 | YOLOv11 / SAM 2 / Open3D | Object detection, segmentation, 3D processing | Images / point clouds | Detections / masks / registered geometry | **Disclosed but unattached to any committed feature.** See R-10 and §6.4 |

### 19.3 M-01 — CAD–BOM confidence scoring (the primary ML component)

**Feature vector:**

| Signal | Description | Deterministic threshold |
|---|---|---|
| 1 — Geometry hash | SHA-256 topology hash vs BOM annotation field | Exact match = 100% confidence |
| 2 — Part name similarity | Levenshtein + token-set-ratio | ≥0.85 = positive match |
| 3 — Mass/weight delta | Computed mass (OCC) vs BOM listed mass | ≤2% tolerance |
| 4 — Assembly position | Bounding-box centroid position | Tiebreaker for ambiguous matches |
| 5 — Material & specification match | Attribute comparison | Configurable |
| 6 — Assembly hierarchy consistency | Parent-child structure agreement | Configurable |
| 7 — Historical matching behaviour | Prior confirmed match patterns | Phase 2 only |

**Output thresholds:** confidence <0.6 → manual review flag; ≥0.85 → auto-confirmed. Both configurable.

**Cold-start behaviour:** where no historical data exists, the system uses deterministic-only matching — a component matches if name similarity ≥0.85 **AND** mass delta ≤5%, with geometry hash as tiebreaker. **Full CAD–BOM sync functionality is available with zero training data.** ML activates in Phase 2 once labelled data is available and validated.

**Training data target:** ≥500 matched CAD-BOM pairs and ≥100 known mismatch examples per discrepancy type, generated during Phase 0 data audit from MDL's historical BOM and CAD archives.

**Scope limitation:** retrained per ship class. **Cross-class generalisation is not assumed** and must not be claimed.

### 19.4 Training data sources

- Historical CAD–BOM reconciliation records
- Engineering Change Requests / Orders (ECR/ECO)
- Design revision history
- Approved BOM modifications
- Compliance review outcomes
- Historical design change propagation records
- Engineer-validated feedback from production deployment

### 19.5 Training process

| Aspect | Approach |
|---|---|
| Data split | 70% train / 15% validation / 15% test, with revision histories from the same project kept **unsplit** to prevent leakage |
| Cross-validation | 5-fold, to evaluate stability and generalisation under limited labelled data |
| Hyperparameter optimisation | Grid search or Bayesian optimisation on validation performance |
| Model selection | Only models showing consistent performance across folds **and** meeting predefined engineering accuracy thresholds are considered for deployment |
| Limited-data strategies | Transfer learning from pre-trained engineering language models; synthetic datasets via controlled rule and design variations; augmentation via valid geometric and metadata transformations; few-shot learning for new equipment categories; active learning prioritising engineer-reviewed corrections |
| Location | **Entirely within MDL's secure on-premise infrastructure.** No production data leaves the shipyard |

### 19.6 Model evaluation & metrics

| Metric | Definition |
|---|---|
| Precision | Percentage of flagged deviations that are genuinely incorrect |
| Recall | Percentage of actual deviations successfully detected |
| F1 | Harmonic mean of precision and recall |
| ROC-AUC | Where applicable |
| CAD–BOM match accuracy | Task-specific |
| Compliance detection accuracy | Task-specific |
| False positive rate | Tracked separately — drives engineer trust |
| False negative rate | Tracked separately — **the safety-critical metric** |
| Mean processing time | Throughput |
| Dimensional error distribution / coordinate deviation | For geometry-based comparison where applicable |

Performance targets are jointly established with MDL during pilot deployment and continuously monitored through validation dashboards.

### 19.7 Model limitations & assumptions

| # | Limitation |
|---|---|
| L-01 | M-01 is trained per ship class; performance on an unseen ship class is not predictable and must be re-validated |
| L-02 | M-01 requires ≥500 matched pairs to activate meaningfully; below that, deterministic mode is the honest answer |
| L-03 | M-02 (NSGA-II) requires ≥3 quantifiable bounded parameters; below that it degrades to sensitivity analysis, which is a weaker product |
| L-04 | Compliance accuracy is bounded by **rule digitisation completeness**, not by any model. An undigitised rule cannot be violated in the system's view. This is the origin of R-02 |
| L-05 | Impact propagation accuracy is bounded by **graph completeness**. A missing edge produces a silent false negative — hence the ≥95% coverage gate |
| L-06 | The GenAI layer can only answer from retrieved approved documents; it will decline rather than speculate, which some users will experience as unhelpfulness |
| L-07 | OCR quality on poor scans directly limits rule and drawing metadata extraction |
| L-08 | No online learning: the system does not improve during operation without a deliberate offline retraining cycle |

### 19.8 Model monitoring

- Continuous evaluation against labelled engineering validation datasets.
- Validation dashboard surfacing precision, recall, F1, FPR, FNR and mean processing time.
- Version-controlled models with full traceability of training data, parameters, evaluation metrics and approval records.
- **No online or autonomous learning in production.** Updates only through controlled offline retraining plus formal engineering approval.
- Independent validation, regression testing, bias assessment and engineering review before any model deployment.

### 19.9 AI/ML pipeline

```
Historical engineering data (on-premise)
   ▼
Labelling / SME validation
   ▼
Split (70/15/15, project-aware, leakage-guarded)
   ▼
Train (5-fold CV, grid/Bayesian HPO)
   ▼
Evaluate (precision, recall, F1, FPR, FNR vs engineering thresholds)
   ▼
Independent validation + regression + bias assessment + engineering review
   ▼
Version + register artefact (object store, full lineage)
   ▼
Deploy (CPU inference; GPU only for training)
   ▼
Monitor (validation dashboard)
   ▼
Engineer corrections ──► active learning queue ──► next offline retraining cycle
```

### 19.10 RAG architecture (non-core layer)

| Element | Specification |
|---|---|
| Knowledge sources | Classification society rule books; national and international engineering standards; MDL engineering procedures; historical approved engineering revisions; design documentation; technical manuals; BOM metadata; Unified Component Registry metadata |
| Document processing | Parsed, OCR-processed where required, segmented into semantically meaningful units — clauses, chapters, tables, specifications. Each chunk preserves document identifier, section number, revision info and source reference |
| Embedding | Sentence Transformers, all-mpnet-base-v2 |
| Vector store | Qdrant, local, with metadata (document version, discipline, revision, source) |
| Retrieval | Query embedding → vector retrieval → metadata filter validation → **only retrieved context passed to the LLM** |
| Grounding | Every generated response cites its source documents. Rule citations remain visible |
| Hallucination controls | Retrieval restricted to approved documents; mandatory citation; low-confidence retrieval returns "Insufficient evidence" rather than speculation; engineering decisions produced by deterministic engines, never the LLM |

### 19.11 Prompt specifications

> **Not yet defined.** System prompts, retrieval templates, refusal templates and citation formats for the GenAI layer. **Trigger:** GenAI layer development, Phase 3 — and only after all mandatory capability is complete. Deliberately unspecified now to avoid investing design effort in a deferrable module.

---

## 20. Knowledge Sources, Knowledge Graph & Rules Engine

### 20.1 Engineering & classification standards in the rule framework

| Standard / Framework | Application within AURORA |
|---|---|
| **IRS** Rules for Construction and Classification of Ships | **Primary** reference framework for naval and maritime compliance validation |
| **IACS** Unified Requirements | Baseline requirements applicable across multiple society evaluations |
| **Lloyd's Register** Rules and Regulations for Ships | Multi-society compliance evaluation and rule conflict analysis |
| **DNV** Rules for Classification | Engineering rule validation and deterministic compliance evaluation |
| **Bureau Veritas** Rules for Steel Ships | Secondary classification framework for multi-society validation |
| **ABS** Rules for Building and Classing Marine Vessels | Secondary classification reference framework |
| **ISO 10303 (STEP)** | Neutral CAD and engineering data exchange interoperability |
| **IEC 60092** series | Marine electrical installation validation references |
| **IEC 61084-1** | Cable management and routing validation references |
| **MIL-STD** requirements | Defence-specific requirements where applicable |
| MDL engineering procedures | Shipyard-specific internal rules |

Final operational rule scope, coverage depth and society mappings to be jointly agreed with MDL during implementation.

### 20.2 Rule digitisation approach

1. Rules extracted from source documents by **template-based parsing** with SME validation loops.
2. Initial scope limited to **high-impact rules**: structural, material, load cases.
3. Coverage: **Phase 1 top ~30% critical rules** by severity and frequency; Phase 2 expanded coverage.
4. **Each rule undergoes SME sign-off before activation in the engine.** No exceptions.
5. Catalog versioned with `effective_date`; superseded rules retained for historical compliance checks.
6. Rule test suite with known-good and known-bad fixtures per rule, run as regression.
7. Air-gapped updates delivered as PKI-signed offline packages, validated before installation.
8. Rules compile to **Drools** rule assets — authoring decoupled from application source code, satisfying NFR-09 and NFR-10.

### 20.3 Compliance evaluation workflow

```
For each component:
  ├─ Query all rule_bindings linked via RULE_GOVERNS edges
  ├─ Filter applicable rules by evaluating conditional_expression against current attributes
  ├─ For LOAD_CASE rules: query simulation_refs for FEA/CFD results, evaluate against limit
  ├─ Evaluate each applicable rule → PASS / FAIL / WARNING
  ├─ On contradictory limits between societies:
  │     apply the more conservative value
  │     raise MULTI_SOCIETY_CONFLICT for engineering review
  └─ Emit finding: rule_id, clause reference, actual value, limit value,
                   severity, confidence, evidence chain
```

**Delta mode** (change-triggered): on geometry-hash change, extract the changed component's delta attributes, compare against previous state, and re-evaluate **only rules whose `conditional_expression` references the changed attributes**. Findings labelled `TRIGGERED_BY_CHANGE` with the specific attribute delta cited (e.g. *"thickness increased from 8mm to 12mm → triggers IRS-STRUCT-3.2.1 minimum thickness check"*). Delta mode operates only after an initial full baseline scan has been recorded for that component.

This is what makes T1 output **change-scoped rather than a full-system compliance dump** — the difference between a usable report and an ignored one.

---

## 21. Algorithms, Formulas & Decision Logic

### 21.1 Impact propagation formula

```
Impact(n) = Impact(parent) × EdgeWeight(parent→n) × e^(−λ × depth)
```

| Parameter | Value | Meaning |
|---|---|---|
| `Impact(root)` | 1.0 | The changed node always has full impact |
| `EdgeWeight` | [0, 1] | Calibrated per edge; high weight = strong coupling |
| `λ` (decay) | 0.3 | Depth decay constant; prevents low-relevance nodes reaching reports |
| `θ` (threshold) | 0.05 | Nodes with `Impact(n) < θ` are pruned from output |
| Depth limit | 6 hops (default) | Tunable per project type |
| Multi-path accumulation | max across all paths | Conservative upper bound — deliberately over- rather than under-estimates |

Traversal is a modified breadth-first search from the changed component.

### 21.2 Topology hashing

Deterministic SHA-256 over sorted `{face_area, edge_length, vertex_coordinates}`. Enables geometry change detection without full re-parsing, and provides the join signal for CAD–BOM Signal 1 and for drawing staleness detection.

### 21.3 NSGA-II configuration

| Parameter | Value |
|---|---|
| Algorithm | NSGA-II (Non-dominated Sorting Genetic Algorithm II), pymoo |
| Population size | 200 individuals |
| Generations | up to 200 |
| Objectives | weight, cost, compliance |
| Output | Pareto front of non-dominated alternatives |
| Activation gate | ≥3 quantifiable design parameters with defined bounds |
| Fallback | Documented parameter sensitivity analysis |

### 21.4 Thresholds & tolerances (defaults — all configurable)

| Parameter | Default | Configurable at |
|---|---|---|
| CAD–BOM name similarity | ≥0.85 | Global / discipline / component type |
| CAD–BOM mass delta (ML mode) | ≤2% | Global / discipline / component type |
| CAD–BOM mass delta (cold-start mode) | ≤5% | Global / discipline / component type |
| Match confidence — manual review | <0.6 | Global |
| Match confidence — auto-confirm | ≥0.85 | Global |
| Impact decay λ | 0.3 | Project |
| Impact prune threshold θ | 0.05 | Project |
| Propagation depth limit | 6 hops | Project / vessel type |
| Graph completeness go-live gate | ≥95% | Programme |

Engineering tolerances are configurable at **five levels**: project, discipline, equipment type, component category, individual engineering parameter. Specific thresholds, validation criteria, deviation severity levels and acceptance limits are to be **finalised through mutual agreement with MDL during implementation** — they are not vendor-set.

### 21.5 Decision logic — finding disposition

```
Finding generated
   ▼
Confidence + severity assessed
   ▼
├─ Low risk AND high confidence ──► Auto-Approved (no engineer action required)
└─ Medium/high risk OR confidence below threshold ──► Engineer Review Required
        ▼
   Engineer can: approve │ reject │ override with mandatory justification
        ▼
   All outcomes → immutable audit trail (timestamp, user ID, justification)
        ▼
   Approved → next workflow stage
```

**No autonomous approval path exists.** Auto-Approved means "no engineer action required on this finding", not "the system approved a design change".

### 21.6 Severity taxonomies

| Context | Levels |
|---|---|
| Rule severity | CRITICAL / MAJOR / MINOR / ADVISORY |
| Compliance status | PASS / FAIL / WARNING |
| Finding severity | Critical / Major / Minor / Informational |
| Impact risk category | CRITICAL (red) / HIGH (orange) / MEDIUM (amber) / LOW (green) |
| Drawing status | CURRENT / STALE / PENDING_APPROVAL / READY_FOR_PRODUCTION |
| Confidence presentation | High / Medium / Low (with underlying evidence) |

### 21.7 Discrepancy type taxonomy (CAD–BOM)

`MISSING` · `EXTRA` · `QUANTITY_MISMATCH` · `MASS_MISMATCH` · `MATERIAL_MISMATCH` · `DUPLICATE` · `REVISION_MISMATCH` · `DRAWING_STALE`

### 21.8 Deviation analysis approach

| Deviation type | Method |
|---|---|
| Positional | Component placement compared against approved design coordinates |
| Dimensional | Extracted geometric properties compared with approved design specifications |
| CAD–BOM | Missing, extra, mismatched or inconsistent components |
| Compliance | Design parameters validated against applicable class rules, standards, regulations |

### 21.9 Configuration parameters & constants

> **Partially defined.** The thresholds in §21.4 are the known defaults. The full configuration parameter catalogue — every tunable, its type, range, default and scope — is a Phase 1 deliverable. **Trigger:** D3 (Pilot AI Platform).

---
## 22. Feature Definitions

Complete inventory. **348 features across 24 modules.** Every feature carries a stable ID, priority, traceability and target phase.

**Priority codes:** `M` = mandatory per SoW · `D` = desirable per SoW · `P` = Arcaisys commitment beyond SoW · `L` = low priority / non-core, build last · `C` = conditional, pending MDL decision.

**Phase codes:** `P0` Capability Demonstration (pre-start) · `P1` Pilot/MVP (M0–M6) · `P2` Full Development (M6–M10) · `P3` Secure Deployment & Scale (M10–M12).

### 22.1 Data Ingestion & Normalisation (`ING`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-ING-01 | Ingest detail design parameters from CAD, PLM and spreadsheets | M | FR-01 | P1 |
| F-ING-02 | Ingest 3D CAD models — STEP, IGES, IFC and native formats | M | FR-02, FCM-2 | P1 |
| F-ING-03 | Extended 3D format support — JT, CATIA V5/V6, NX, SolidWorks via OCC/PythonOCC | P | D-08 | P2 |
| F-ING-04 | Ingest and parse BOM from ERP / PLM / spreadsheet (CSV, XML, XLSX) | M | FR-03 | P1 |
| F-ING-05 | Ingest 2D production and basic drawings — PDF, TIFF, DWG, DXF | P | FCM-1 | P1 |
| F-ING-06 | OCR pipeline for scanned drawings and scanned rule documents (Tesseract) | M | FR-04 | P1 |
| F-ING-07 | Ingest class rules, standards and regulations (PDF, scanned, structured) | M | FR-04 | P1 |
| F-ING-08 | Ingest FEA/CFD simulation results and link them to components | P | D-01 | P2 |
| F-ING-09 | Format auto-detection and conversion to a single internal geometry representation (BREP) | P | D-08 | P1 |
| F-ING-10 | Shape healing — repair degenerate geometry, zero-area faces, gaps, inconsistent orientations | P | D-08 | P1 |
| F-ING-11 | Assembly decomposition — XCAF tree traversal, component ID assignment, parent-child extraction | P | D-08 | P1 |
| F-ING-12 | Geometric property computation — volume, surface area, bounding box, centroid, CoG, inertia tensor | P | D-01, D-08 | P1 |
| F-ING-13 | Topology hashing (SHA-256 over sorted geometric primitives) for change detection without re-parsing | P | D-08 | P1 |
| F-ING-14 | Metadata extraction from drawings — drawing number, revision, title block, annotations, dimensions | P | FCM-1 | P1 |
| F-ING-15 | Ingestion-time data validation — missing attributes, conflicting values, duplicates, unsupported formats, unresolved references | P | NFR-04 | P1 |
| F-ING-16 | Graceful degradation on incomplete input — continue on validated data, explicitly flag gaps and confidence limits | P | NFR-04 | P1 |
| F-ING-17 | REST ingestion API with JSON schema validation | D | FR-26 | P2 |
| F-ING-18 | Batch ingestion of large rule sets, BOMs and full-ship CAD assemblies | M | NFR-05 | P2 |
| F-ING-19 | Fallback ingestion bridges for legacy/custom CAD formats not supported natively | P | Risk mitigation | P2 |

---

### 22.2 Unified Component Registry / Digital Twin Core (`DTC`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-DTC-01 | Single source of truth: one unified digital representation per ship component | P | D-01 | P1 |
| F-DTC-02 | Globally unique `component_id` (UUID) linked to both CAD assembly path and BOM part number | P | D-01 | P1 |
| F-DTC-03 | Geometry feature store — bounding box, surface area, volume, centroid, moments of inertia, topology hash | P | D-01 | P1 |
| F-DTC-04 | Material attribute store — material code, grade, density, yield strength, UTS, thermal conductivity, corrosion class | P | D-01 | P1 |
| F-DTC-05 | Mass property store — mass, centre of gravity (x/y/z), inertia tensor | P | D-01 | P1 |
| F-DTC-06 | BOM entry linkage — part number, description, quantity, unit cost, supplier code, lead time | P | D-01 | P1 |
| F-DTC-07 | Rule bindings per component — rule ID, society, parameter name, limit value, limit type | P | D-01 | P1 |
| F-DTC-08 | Simulation references per component — type, file path, result summary, pass/fail, timestamp | P | D-01 | P2 |
| F-DTC-09 | Per-component version history with timestamp, author, change description and delta hash | M | FR-17 | P1 |
| F-DTC-10 | End-to-end traceability chain: design parameter ↔ rule ↔ BOM item ↔ 3D model ↔ drawing | M | FR-15 | P1 |
| F-DTC-11 | Registry scalable to full-ship assemblies (10,000+ nodes target; enterprise tier beyond) | M | NFR-06 | P2 |

---

### 22.3 Rule Knowledge Base & Rule Digitisation (`RKB`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-RKB-01 | Searchable, versioned knowledge base of class rules, standards and regulations | M | FR-05 | P1 |
| F-RKB-02 | Structured rule catalog schema — `rule_id`, class society, rule type, severity, effective date, conditional expression, limit values | P | D-10 | P1 |
| F-RKB-03 | Rule types supported — dimensional limit, material requirement, process requirement, arrangement requirement, load case, environmental condition | P | D-10 | P1 |
| F-RKB-04 | Severity taxonomy — CRITICAL / MAJOR / MINOR / ADVISORY | P | D-10 | P1 |
| F-RKB-05 | Multi-society rule libraries — IRS, Lloyd's Register, DNV, Bureau Veritas, ABS, IACS UR, ISO, MIL-STD, MDL internal procedures | P | D-10 | P1 (subset) / P2 (full) |
| F-RKB-06 | Domain standards integrated — ISO 10303 (STEP), IEC 60092 series (marine electrical), IEC 61084-1 (cable management) | P | Concept Note §6.2 | P2 |
| F-RKB-07 | Template-based rule extraction pipeline from source rule documents | P | D-10 | P1 |
| F-RKB-08 | SME validation and mandatory sign-off workflow before any rule is activated in the engine | P | QA framework | P1 |
| F-RKB-09 | Rule test fixtures — known-good and known-bad cases per rule, run as regression suite | P | QA framework | P1 |
| F-RKB-10 | Rule versioning with `effective_date`; superseded rules retained for historical/retrospective compliance checks | M | NFR-09, FR-05 | P1 |
| F-RKB-11 | Rule catalog updatable without vendor code changes (admin-editable, configuration-driven) | M | NFR-09, NFR-10 | P2 |
| F-RKB-12 | Air-gapped rule update mechanism — PKI/cryptographically signed offline update packages with integrity validation before install | M | NFR-01, NFR-09 | P2 |
| F-RKB-13 | Defined periodic (e.g. quarterly) rule-refresh process documented in the Field Operations Manual | P | Risk mitigation | P3 |
| F-RKB-14 | Protection of licensed class-rule content — no redistribution, access-controlled storage | M | NFR-03 | P2 |
| F-RKB-15 | Phased rule coverage tracking — Phase 1 top ~30% critical rules by severity/frequency, expanding in Phase 2, with coverage reporting | P | D-10 | P1 |
| F-RKB-16 | Configurable engineering tolerances at global, project, discipline, equipment-type, component-category and individual-parameter level | M | NFR-10 | P1 |
| F-RKB-17 | Compilation of digitised rules into Drools rule assets, with rule authoring/editing decoupled from application source code | M | NFR-09, NFR-10 | P1 |

---

### 22.4 Dependency Knowledge Graph (`KG`)

Implemented on **ArcadeDB** (multi-model, Apache 2.0, Italy-origin — satisfies the land-border sovereignty constraint).

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-KG-01 | Directed weighted dependency graph `G = (V, E, W)` as the single source of truth for inter-system reasoning | P | D-02 | P1 |
| F-KG-02 | Automatic `ASSEMBLY_CHILD` edge population from CAD hierarchy during ingestion | P | D-02 | P1 |
| F-KG-03 | `PHYSICAL_INTERFACE` edge derivation via interference/bounding-box intersection and gap analysis | P | D-02 | P1 |
| F-KG-04 | `STRUCTURALLY_SUPPORTS` edges weighted by load-sharing ratio | P | D-02 | P1 |
| F-KG-05 | `ELECTRICALLY_FEEDS` edges weighted by voltage/current dependency ratio | P | D-02 | P2 |
| F-KG-06 | `THERMALLY_ADJACENT` edges weighted by spatial proximity factor | P | D-02 | P2 |
| F-KG-07 | `ROUTED_THROUGH` edges (cable/pipe through structure) weighted by contact area ratio | P | D-02 | P2 |
| F-KG-08 | `MECHANICALLY_CONNECTED` edges weighted by contact area / joint stiffness | P | D-02 | P2 |
| F-KG-09 | `RULE_GOVERNS` edges linking classification rules to components, weighted by rule criticality | P | D-02 | P1 |
| F-KG-10 | `FUNCTIONAL_DEPENDENCY` edges from rule catalog and SME-maintained dependency matrix | P | D-02 | P2 |
| F-KG-11 | Graph completeness validation — isolated-node detection, ≥95% of BOM line items with ≥1 edge as a go-live gate | P | Concept Note §3.5 | P1 |
| F-KG-12 | Graph completeness dashboard panel with real-time coverage metrics | P | Concept Note §3.5 | P1 |
| F-KG-13 | Configurable edge-weight calibration, SME-reviewed | P | D-02 | P1 |
| F-KG-14 | Graph query interface for dependency interrogation (ArcadeDB — SQL/Cypher/Gremlin query surface) | P | D-02 | P2 |
| F-KG-15 | Institutional knowledge retention — persistent mapping of ship-system interdependencies, historical rule interpretations, and change-propagation patterns across vessel programmes | P | Concept Note §7.4 | P3 |

---

### 22.5 CAD–BOM Synchronisation Engine (`SYN`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-SYN-01 | Automated consistency check between 3D model and BOM | M | FR-13 | P0/P1 |
| F-SYN-02 | Signal 1 — geometry/topology hash matching against BOM annotation | P | D-09 | P1 |
| F-SYN-03 | Signal 2 — part name/description similarity (Levenshtein, token-set ratio; threshold ≥0.85) | P | D-09 | P1 |
| F-SYN-04 | Signal 3 — mass/weight delta comparison against configurable tolerance (default ≤2%) | P | D-09 | P1 |
| F-SYN-05 | Signal 4 — assembly position / bounding-box centroid as tiebreaker for ambiguous matches | P | D-09 | P1 |
| F-SYN-06 | Signal 5 — material and specification matching | P | Questionnaire §7.4 | P1 |
| F-SYN-07 | Signal 6 — assembly hierarchy consistency check | P | Questionnaire §7.4 | P1 |
| F-SYN-08 | Signal 7 — historical matching behaviour as an evidence input | P | Questionnaire §7.4 | P2 |
| F-SYN-09 | ML confidence scoring producing a 0.0–1.0 match confidence per pair; candidate models benchmarked across XGBoost, LightGBM, Scikit-learn ensembles and PyTorch, best performer selected | M | FR-09, D-09 | P2 |
| F-SYN-10 | Confidence thresholding — `<0.6` route to manual review, `≥0.85` auto-confirm (thresholds configurable) | P | D-09 | P2 |
| F-SYN-11 | Deterministic cold-start mode — full sync operation with no historical training data (name similarity ≥0.85 AND mass delta ≤5%, geometry hash tiebreak) | P | D-09 | P1 |
| F-SYN-12 | Discrepancy type: MISSING component (in CAD, absent in BOM or vice versa) | M | FR-14, FCM-11 | P1 |
| F-SYN-13 | Discrepancy type: EXTRA / ADDED component | M | FR-14, FCM-12 | P2 |
| F-SYN-14 | Discrepancy type: QUANTITY mismatch | M | FR-14 | P1 |
| F-SYN-15 | Discrepancy type: MASS_MISMATCH beyond tolerance | M | FR-14 | P1 |
| F-SYN-16 | Discrepancy type: MATERIAL_MISMATCH / specification difference | M | FR-14 | P1 |
| F-SYN-17 | Discrepancy type: DUPLICATE record | P | D-09 | P1 |
| F-SYN-18 | Discrepancy type: REVISION_MISMATCH between CAD and BOM revision states | P | D-09 | P1 |
| F-SYN-19 | Structured discrepancy report with CAD value vs BOM value, delta, per-signal scores and confidence | M | FR-21 | P1 |
| F-SYN-20 | "Update BOM from CAD" controlled action with engineer confirmation | P | Case study §3 | P2 |
| F-SYN-21 | Bulk actions — accept match / flag for manual review / escalate | P | Dashboard spec | P2 |
| F-SYN-22 | Sync history log with timestamps and per-run summary | P | Dashboard spec | P2 |
| F-SYN-23 | Bi-directional BOM synchronisation with ERP | D | FR-26 | P2 |
| F-SYN-24 | Positional deviation detection — component placement vs approved design coordinates | P | Questionnaire §6.5 | P2 |
| F-SYN-25 | Dimensional deviation detection — extracted geometry vs approved design specification | P | Questionnaire §6.5, FCM-13 | P2 |
| F-SYN-26 | Equipment relocation detection | P | FCM-10 | P1 |
| F-SYN-27 | Route change detection (pipe/duct/cable rerouting) via CAD topology analysis | P | FCM-9 | P2 |
| F-SYN-28 | Deviation severity classification against configurable tolerances | P | FCM-14 | P1 |

---

### 22.6 Compliance Validation Engine (`CMP`)

Rule evaluation is executed by the **Drools** deterministic rule engine. Digitised rules from the catalog (§3) compile to Drools rule assets; Drools guarantees the repeatability required by NFR-04.

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-CMP-01 | Automatic check of design parameters against class rules, standards and regulations | M | FR-06 | P0/P1 |
| F-CMP-02 | Deterministic evaluation — identical inputs always produce identical outputs | P | D-10, NFR-04 | P1 |
| F-CMP-03 | Flag non-compliance with citation to the specific rule/clause (e.g. `IRS-2024-STRUCT-3.2.1`) | M | FR-07, FR-20 | P0/P1 |
| F-CMP-04 | Per-finding output of actual value, allowable limit and units in plain engineering terms | P | Usability provisions | P1 |
| F-CMP-05 | Baseline compliance scan — full-system evaluation across all registered components | P | D-10 | P1 |
| F-CMP-06 | Change-triggered (delta) compliance mode — re-evaluate only rules whose conditional expressions reference changed attributes | P | D-10 | P2 |
| F-CMP-07 | Findings labelled `TRIGGERED_BY_CHANGE` with the specific attribute delta cited (e.g. thickness 8mm → 12mm) | P | D-10 | P2 |
| F-CMP-08 | Change-triggered findings displayed separately from baseline findings | P | Usability provisions | P2 |
| F-CMP-09 | Load-case rule evaluation using ingested FEA/CFD simulation results | P | D-10 | P2 |
| F-CMP-10 | Multi-society conflict detection — flag `MULTI_SOCIETY_CONFLICT` where societies specify contradictory limits | P | D-10 | P2 |
| F-CMP-11 | Conservative-value resolution policy applied automatically on multi-society conflict, surfaced for engineering review | P | D-10 | P2 |
| F-CMP-12 | Compliance status taxonomy — PASS / FAIL / WARNING per rule per component | P | Dashboard spec | P1 |
| F-CMP-13 | Severity classification of findings — Critical / Major / Minor / Informational | P | Questionnaire §6.6 | P1 |
| F-CMP-14 | Confidence score per compliance determination, derived from rule-match completeness, parameter availability, input data quality, rule ambiguity and constraints satisfied | M | FR-09 | P1 |
| F-CMP-15 | Confidence presented as High / Medium / Low with the underlying evidence exposed | P | Questionnaire §7.4 | P1 |
| F-CMP-16 | Low-confidence findings automatically routed to engineering review before approval | P | HITL layer | P1 |
| F-CMP-17 | Retrospective compliance evaluation against superseded rule versions | P | F-RKB-10 | P2 |
| F-CMP-18 | Design-optimization suggestions with respect to class rules and standards | D | FR-08 | P2 |
| F-CMP-19 | Recognition of affected systems in a compliance context (knowledge-graph driven) | P | FCM-6 | P1 |
| F-CMP-20 | Recognition of ventilation / HVAC duct systems as a distinct compliance domain | P | FCM-7 | P2 |
| F-CMP-21 | Recognition of equipment / machinery entities via entity extraction and dependency mapping | P | FCM-8 | P2 |

---

### 22.7 Change Impact Prediction & Propagation (`IMP`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-IMP-01 | Predict downstream change impacts across disciplines — hull, propulsion, weapons, electrical, systems | M | FR-10 | P1 |
| F-IMP-02 | Graph traversal propagation engine (modified BFS/DFS) from the changed component | P | D-03 | P1 |
| F-IMP-03 | Weighted impact scoring with exponential depth decay: `Impact(n) = Impact(parent) × EdgeWeight × e^(−λ·depth)` | P | D-03 | P1 |
| F-IMP-04 | Configurable pruning threshold (default θ = 0.05) to suppress low-relevance nodes | P | D-03 | P1 |
| F-IMP-05 | Multi-path accumulation using maximum score across paths (conservative upper bound) | P | D-03 | P1 |
| F-IMP-06 | Configurable propagation depth limit (default 6 hops), tunable per project/vessel type | P | D-03 | P1 |
| F-IMP-07 | Ranked impacted-component list with impact scores | M | FR-10 | P1 |
| F-IMP-08 | Explicit propagation path explanation per impacted component (root dependency path) | M | FR-20 | P1 |
| F-IMP-09 | Risk category badge per affected component — CRITICAL / HIGH / MEDIUM / LOW | P | Dashboard spec | P1 |
| F-IMP-10 | Flag structural re-analysis requirements arising from a change | M | FR-11 | P2 |
| F-IMP-11 | Flag weight-redistribution impacts (mass, CoG shift) | M | FR-11 | P2 |
| F-IMP-12 | Flag re-qualification / testing & trials impacts | M | FR-12 | P2 |
| F-IMP-13 | Detect downstream compliance implications of a change (chained into F-CMP-06) | P | D-03 | P2 |
| F-IMP-14 | Change request input form — component ID, change type, magnitude | P | Dashboard spec | P1 |
| F-IMP-15 | Targeted re-validation scoping — validate only affected domains rather than full system | P | Annexure 1 | P2 |
| F-IMP-16 | Interactive propagation graph visualisation, filterable by ship system / deck, colour-coded by severity | D | FR-22 | P2 |
| F-IMP-17 | Impact analysis response within a few seconds for standard subsystem propagation | M | NFR-05 | P2 |

---

### 22.8 Design Optimisation Engine (`OPT`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-OPT-01 | Multi-objective design optimisation across weight, cost and compliance objectives | D | FR-08, D-11 | P2 |
| F-OPT-02 | NSGA-II genetic algorithm implementation (pymoo), population 200, up to 200 generations | P | D-11 | P2 |
| F-OPT-03 | Pareto front output of non-dominated design alternatives | P | D-11 | P2 |
| F-OPT-04 | Pareto front scatter plot visualisation (weight vs cost vs compliance score) | P | Dashboard spec | P2 |
| F-OPT-05 | Side-by-side trade-off comparison of any two candidate solutions | P | Dashboard spec | P2 |
| F-OPT-06 | Rule-based pre-filtering of infeasible candidates before optimisation | P | D-11 | P2 |
| F-OPT-07 | Activation gate — requires ≥3 quantifiable design parameters with defined bounds | P | D-11 | P2 |
| F-OPT-08 | Fallback: documented parameter sensitivity analysis when optimisation preconditions are not met | P | D-11 | P2 |
| F-OPT-09 | Parameter sensitivity chart driven by SHAP values | P | Dashboard spec | P2 |
| F-OPT-10 | Export selected solution as a design recommendation report | P | Dashboard spec | P2 |
| F-OPT-11 | All optimisation outputs marked advisory; no autonomous adoption of any alternative | M | Scope boundary | P2 |
| F-OPT-12 | Optional PyTorch surrogate model for FEA acceleration (post-pilot enhancement; degrades gracefully with no GPU) | P | D-11 | P3 |

---

### 22.9 Drawing Synchronisation & Revision Engine (`DRW`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-DRW-01 | Support incorporation of finalised design into **basic drawings** before class submission | M | FR-16 | P2 |
| F-DRW-02 | Incorporate the **class-approved revision into production drawings** post-approval | M | FR-18 | P2 |
| F-DRW-03 | Automatic identification of all drawings linked to affected components (via PLM metadata) | P | D-13 | P2 |
| F-DRW-04 | Drawing status taxonomy — CURRENT / STALE / PENDING_APPROVAL / READY_FOR_PRODUCTION | P | D-13 | P2 |
| F-DRW-05 | `DRAWING_STALE` discrepancy detection via geometry-hash mismatch between drawing and current CAD state | P | D-13 | P2 |
| F-DRW-06 | DXF title block update — programmatic edit of REV, DATE, DESCRIPTION attributes by layer convention (ezdxf) | P | D-13 | P2 |
| F-DRW-07 | Revision cloud generation on DXF — LWPOLYLINE entities on a dedicated REVCLOUD layer around the changed component's 2D projection | P | D-13 | P2 |
| F-DRW-08 | Revision cloud preview in the UI before commit | P | Dashboard spec | P2 |
| F-DRW-09 | PDF drawing revision annotation overlay stamped onto approved PDFs | P | D-13 | P2 |
| F-DRW-10 | Automatic revision increment (Rev N → Rev N+1) with change delta logged | M | FR-17 | P2 |
| F-DRW-11 | Per-drawing diff view — current vs previous revision with changed attributes highlighted | D | FCM-19 | P2 |
| F-DRW-12 | Production release queue with one-click "Ready for Production" bundle download | P | D-13 | P2 |
| F-DRW-13 | CAD re-export trigger via CAD-system webhook for parametric drawing formats (CATIA `.CATDrawing`, NX `.prt`) that cannot be edited directly | P | D-13 | P2 |
| F-DRW-14 | PLM drawing vault integration (Teamcenter / Windchill) with file-system folder-watch fallback | P | D-13 | P2 |
| F-DRW-15 | Traceable linkage between each engineering change and its resulting drawing revisions | M | FR-15, NFR-12 | P2 |
| F-DRW-16 | Automated end-to-end drawing revision workflow chain: hash change → impact → BOM update → compliance → drawing flag → engineer review → revision increment → production queue | P | Annexure 2 §5.7 | P2 |

---

### 22.10 Configuration, Version & Baseline Management (`CFG`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-CFG-01 | Manage revisions/versions of design data, basic drawings and production drawings | M | FR-17 | P1 |
| F-CFG-02 | Unique identity plus complete version history for every engineering object (component, assembly, CAD model, document, BOM entry, drawing, simulation ref, compliance record) | M | FR-17 | P1 |
| F-CFG-03 | Version metadata — author, timestamp, revision reason, approval status, engineering discipline | P | Questionnaire §5.6 | P1 |
| F-CFG-04 | Local Git-based version control for engineering artefacts, deployed entirely inside the air-gapped environment | P | Questionnaire §5.6 | P2 |
| F-CFG-05 | Immutable design baselines captured at approved milestones | P | Questionnaire §5.6 | P2 |
| F-CFG-06 | Lifecycle stage tags — Contract Design, Basic Design, Class Submission, Class Approved, Production Release | P | Questionnaire §5.6 | P2 |
| F-CFG-07 | Automatic difference detection between any two versions | P | Questionnaire §5.6 | P2 |
| F-CFG-08 | Multi-level version comparison — component, assembly, subsystem and full-ship level | P | Questionnaire §5.6 | P2 |
| F-CFG-09 | Side-by-side visualisation of geometry, BOM, document, compliance-status and dependency changes between versions | D | FCM-19 | P2 |
| F-CFG-10 | Secure archival of older revisions and completed baselines, remaining fully accessible for audit and rollback | P | Questionnaire §5.6 | P2 |
| F-CFG-11 | Guarantee that all analyses run against the correct approved design configuration | M | NFR-12 | P2 |

---

### 22.11 Classification Society Submission Workflow (`CLS`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-CLS-01 | Pre-submission validation — final consistency and compliance check before package generation | P | D-15 | P2 |
| F-CLS-02 | Per-society submission package generation (IRS / LR / DNV / BV / ABS) | P | D-15 | P2 |
| F-CLS-03 | Package content: rule-by-rule compliance findings with rule citation, component ID, parameter value, limit value, pass/fail | P | D-15 | P2 |
| F-CLS-04 | Package content: design calculation summary for structural and stability load cases | P | D-15 | P2 |
| F-CLS-05 | Package content: drawing revision log aligned to current BOM revision state | P | D-15 | P2 |
| F-CLS-06 | Package content: discrepancy and resolution record | P | D-15 | P2 |
| F-CLS-07 | Active submission tracker — submission date, society, status | P | Dashboard spec | P2 |
| F-CLS-08 | Society query ingestion as structured objects (`query_id`, `rule_ref`, `component_id`, `query_text`, `response_due_date`) | P | D-15 | P2 |
| F-CLS-09 | Automatic creation of change requests in the knowledge graph from ingested society queries | P | D-15 | P2 |
| F-CLS-10 | Targeted re-evaluation of affected components' rule bindings triggered by a query | P | D-15 | P2 |
| F-CLS-11 | Query response editor with mandatory justification field and attachment of supporting reports | P | Dashboard spec | P2 |
| F-CLS-12 | Re-submission readiness checker — verifies all queries resolved and engineer-approved | P | D-15 | P2 |
| F-CLS-13 | Automatic re-submission package generation once readiness is confirmed | P | D-15 | P2 |
| F-CLS-14 | Approval cycle history per drawing package | P | Dashboard spec | P2 |
| F-CLS-15 | Full lifecycle support: Pre-submission → Submit → Receive queries → Resolve → Re-validate → Re-submit | P | D-15 | P2 |
| F-CLS-16 | **Boundary:** no automated submission to any classification-society portal; submission remains a controlled manual activity | M | SoW §5.2 | — |

---

### 22.12 Review, Approval & Human-in-the-Loop Workflow (`WKF`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-WKF-01 | Review & approval workflow with disposition: accept / reject / refer | M | FR-19, FCM-20 | P1 |
| F-WKF-02 | Mandatory engineer review checkpoint before any approval action — no autonomous approvals | M | HITL layer | P1 |
| F-WKF-03 | Finding categorisation at output time — Auto-Approved (low risk, high confidence) vs Engineer Review Required | P | HITL layer | P2 |
| F-WKF-04 | Engineer override of any system decision, with a mandatory free-text justification | P | HITL layer | P1 |
| F-WKF-05 | Every override recorded in the immutable audit trail with timestamp, user ID and justification text | M | FR-25, NFR-12 | P1 |
| F-WKF-06 | Digital approval signature on change records by Approver role | P | Concept Note §2.1 | P2 |
| F-WKF-07 | Draft change record auto-generated on detected design change | P | Annexure 2 §5.7 | P2 |
| F-WKF-08 | Controlled exception workflow for deviations requiring engineering judgement — review, approval, justification, traceability | P | Questionnaire §5.4 | P2 |
| F-WKF-09 | Approve / Reject / Request Revision controls on drawings | P | Dashboard spec | P2 |
| F-WKF-10 | Engineer corrections captured as labelled feedback feeding the offline active-learning/retraining queue | P | Questionnaire §7.8 | P3 |
| F-WKF-11 | Escalation path for low-confidence and unresolved items to authorised users | P | Questionnaire §5.5 | P1 |
| F-WKF-12 | Export / hand-off package to the design department for drawing incorporation | P | FCM-18 | P1 |

---

### 22.13 GenAI, RAG & Engineering Assistant (`GAI`) — non-core

**Status: low priority, non-core.** This layer entered scope in the final proposal draft and is not required by any mandatory SoW requirement. It is a usability and productivity enhancement over outputs the deterministic engines already produce. Build it only once every `M`, `D` and `P` item elsewhere in this document is complete and accepted. If the 12-month schedule comes under pressure, this is the first module to defer.

Two constraints are absolute and apply the moment any part of this layer ships: F-GAI-10 and F-GAI-11. They are marked `M` because they gate the layer's release, not because the layer itself is mandatory.

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-GAI-01 | Natural-language query interface over engineering data (plain-English questions about affected systems, non-compliance reasons, impacted compartments) | L | Questionnaire §7.2 | P3 |
| F-GAI-02 | Offline, locally-hosted LLM (e.g. Llama 3.1 8B Instruct) with no external API dependency | L | NFR-01, §8.2 | P3 |
| F-GAI-03 | RAG pipeline over class rule books, standards, MDL procedures, historical approved revisions, design documentation, technical manuals, BOM metadata and registry metadata | L | Questionnaire §7.3 | P3 |
| F-GAI-04 | Semantic chunking that preserves document identifiers, section numbers, revision info and source references | L | Questionnaire §7.3 | P3 |
| F-GAI-05 | Embedding generation (Sentence Transformers, all-mpnet-base-v2) with local vector index (Qdrant) | L | Questionnaire §7.3 | P3 |
| F-GAI-06 | Metadata-filtered retrieval by document version, discipline, revision and source | L | Questionnaire §7.3 | P3 |
| F-GAI-07 | Rule interpretation — engineer-friendly plain-language explanation of dense clauses, always alongside the original cited clause | L | Questionnaire §7.2 | P3 |
| F-GAI-08 | Automated narrative report generation from deterministic engine outputs (executive summaries, compliance narratives, impact narratives) | L | Questionnaire §7.2 | P3 |
| F-GAI-09 | Interactive engineering assistant for contextual explanation of dependency propagation, revision history and BOM inconsistencies | L | Questionnaire §7.2 | P3 |
| F-GAI-10 | Anti-hallucination guardrails — retrieval restricted to approved documents, mandatory source citation on every generated answer, "Insufficient evidence" response on low-confidence retrieval | M (release gate) | NFR-04, FR-20 | P3 |
| F-GAI-11 | Hard architectural boundary — LLM never produces a compliance determination; all engineering decisions come from the deterministic Drools engine | M (release gate) | NFR-04 | P3 |

**Dependency note:** deferring this module has no effect on any mandatory requirement. FR-20 (explainability with source citations) is satisfied by §22.14 through deterministic clause citation, not by the LLM. FR-21 and FR-23 (reports and export) are satisfied by §22.15 through templated generation. Nothing in §22.1–§22.12 or §22.14–§22.23 depends on this layer.

---

### 22.14 Explainability, Confidence & Traceability (`XAI`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-XAI-01 | Every determination grounded in and cited to an authoritative rule/clause | M | NFR-04, FR-20 | P0/P1 |
| F-XAI-02 | Full evidence chain per finding: affected object → CAD component → BOM item → applicable rule → clause reference → input parameters → intermediate validation steps → conclusion → confidence → version IDs | M | FR-20, NFR-07 | P1 |
| F-XAI-03 | Drill-down from dashboard summary to underlying engineering evidence | M | NFR-07 | P1 |
| F-XAI-04 | Confidence score attached to every compliance and optimisation output | M | FR-09, FCM-15 | P1 |
| F-XAI-05 | SHAP-based feature attribution for ML-derived scores (CAD-BOM matching, prioritisation) | P | D-09 | P2 |
| F-XAI-06 | Per-signal score breakdown visible for every CAD-BOM match | P | Usability provisions | P1 |
| F-XAI-07 | No compliance output presented without supporting evidence and source references | M | NFR-04 | P1 |
| F-XAI-08 | 100% of intelligent analytical outputs linked to traceable engineering evidence | P | Concept Note §3.6 | P2 |

---

### 22.15 Reporting & Export (`RPT`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-RPT-01 | Compliance report with clause citations | M | FR-21 | P0/P1 |
| F-RPT-02 | Change-impact prediction report | M | FR-21 | P1 |
| F-RPT-03 | 3D–BOM reconciliation report | M | FR-21 | P1 |
| F-RPT-04 | Disposition records report | M | FR-21, NFR-12 | P2 |
| F-RPT-05 | Revision packages for basic and production drawings | M | FR-21 | P2 |
| F-RPT-06 | Report content: deviation description, affected components and systems, root dependency path, compliance impact, recommended corrective actions, associated revision information | P | Questionnaire §5.7 | P1 |
| F-RPT-07 | Severity-classified deviation list with engineering coordinates, assemblies and subsystem references | P | Questionnaire §6.6 | P1 |
| F-RPT-08 | Visual comparison / overlay of affected CAD assemblies and engineering objects | D | FCM-16 | P2 |
| F-RPT-09 | Automatic report generation (no manual compilation) | P | FCM-17 | P1 |
| F-RPT-10 | Export to PDF | M | FR-23, FCM-24 | P1 |
| F-RPT-11 | Export to standard interchange formats (JSON, CSV, XML) | M | FR-23 | P1 |
| F-RPT-12 | One-click PDF export auto-named with change ID and timestamp | P | Usability provisions | P2 |
| F-RPT-13 | Export of audit trail for compliance documentation | M | FR-25 | P2 |
| F-RPT-14 | Hand-off/export package to design department | P | FCM-18 | P1 |

---

### 22.16 Decision Intelligence Dashboard (`DSH`)

Web application, React + TypeScript, served on-premise with all assets bundled at deployment time and no external browser dependency.

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-DSH-01 | Unified single-pane interface across all engine outputs | D | FR-22, D-12 | P1 |
| F-DSH-02 | **System Health & Status Panel** — engine status indicators, last sync timestamp per source (CAD/BOM/PLM), active job queue (running/queued/failed), data freshness alerts | P | D-12 | P1 |
| F-DSH-03 | **Impact Analysis Panel** — change request form, interactive propagation graph, ranked impacted list, risk badges, PDF/JSON export | P | D-12 | P1 |
| F-DSH-04 | **CAD–BOM Synchronisation Panel** — discrepancy summary table by type with counts, per-discrepancy drill-down, filter by system/deck/severity, bulk actions, sync history | P | D-12 | P1 |
| F-DSH-05 | **Compliance Validation Panel** — component-level PASS/FAIL/WARNING grid, rule citation per finding, change-triggered findings segregated, multi-society conflict flags, submission package export | P | D-12 | P1 |
| F-DSH-06 | **Drawing Synchronisation Panel** — status table, per-drawing diff view, revision cloud preview, approval controls, production release queue | P | D-12 | P2 |
| F-DSH-07 | **Classification Society Workflow Panel** — submission tracker, query inbox, response editor, re-submission readiness checker, approval cycle history | P | D-12 | P2 |
| F-DSH-08 | **Design Optimisation Panel** — Pareto scatter plot, solution comparison table, sensitivity chart, recommendation export | P | D-12 | P2 |
| F-DSH-09 | **Audit Trail Panel** — immutable log view, filters (user, date range, action type, component ID), hash-chain integrity indicator, export | P | D-12 | P2 |
| F-DSH-10 | **Knowledge Graph Coverage Panel** — real-time completeness metrics and isolated-node list | P | Concept Note §3.5 | P1 |
| F-DSH-11 | **Analytics Panel** — change volume, compliance status trend, impact statistics | D | FR-22 | P2 |
| F-DSH-12 | Role-based UI — panels and controls hidden per role to reduce operator error and cognitive load | M | FR-24, NFR-08 | P1 |
| F-DSH-13 | Colour-coded impact severity (CRITICAL red / HIGH orange / MEDIUM amber / LOW green), filterable by ship system or deck | P | Usability provisions | P2 |
| F-DSH-14 | Responsive interaction under standard engineering review workloads; multi-user concurrent support | M | NFR-05, NFR-08 | P2 |
| F-DSH-15 | Usable by design and configuration engineers with minimal training | M | NFR-08 | P2 |

---

### 22.17 Integration & API Layer (`INT`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-INT-01 | REST API gateway exposing all platform capabilities | D | FR-26, FCM-25 | P2 |
| F-INT-02 | Full OpenAPI 3.0 specification published | P | D-05 | P2 |
| F-INT-03 | PLM connectors — Teamcenter, Windchill, ENOVIA (BOM, drawing metadata, revision history, approval status) | D | FR-26, D-05 | P2 |
| F-INT-04 | ERP connectors — SAP PM, Oracle via REST/OData (BOM sync, cost rates, supplier data) | D | FR-26 | P2 |
| F-INT-05 | CAD connectors — CATIA, NX, SolidWorks, AutoCAD via file watcher / on-save webhooks triggering ingestion | D | FR-26, D-05 | P2 |
| F-INT-06 | Configurable webhook endpoints per format | P | D-05 | P2 |
| F-INT-07 | Asynchronous task queue for long-running jobs (CAD parsing, optimisation, ML inference) with REST status polling | P | D-05 | P2 |
| F-INT-08 | Standards-based interchange (STEP/ISO 10303, IGES, JT) to avoid proprietary lock-in | M | NFR-11 | P2 |
| F-INT-09 | Spreadsheet-based BOM import path for environments without direct ERP/PLM access | P | FR-03 | P1 |
| F-INT-10 | Adapter customisation framework aligned to MDL's actual interface specifications, scoped during Phase 0 assessment | P | Phase 0 | P2 |
| F-INT-11 | Independently deployable services allowing parallel execution and horizontal scaling without architectural redesign | M | NFR-06 | P2 |

---

### 22.18 Security, Access Control & Audit (`SEC`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-SEC-01 | Role-based user and access management | M | FR-24, FCM-21 | P1 |
| F-SEC-02 | Four baseline roles — Viewer (read-only), Analyst (run engines, flag), Approver (approve/reject, sign, manage re-submissions), Admin (user management, RBAC config, rule catalog editing, audit administration) | P | Concept Note §2.1 | P1 |
| F-SEC-03 | Authentication modes — local, Microsoft Active Directory, LDAP, enterprise SSO | M | NFR-03 | P2 |
| F-SEC-04 | JWT-based API session management | P | Annexure 2 §5.5.3 | P2 |
| F-SEC-05 | Encryption at rest — AES-256 via database-level, disk-level and encrypted-volume mechanisms, configurable to MDL policy | M | NFR-03 | P2 |
| F-SEC-06 | Encryption in transit — TLS 1.3 / HTTPS with customer-managed certificates | M | NFR-03 | P2 |
| F-SEC-07 | Complete audit trail of all user and system actions | M | FR-25, FCM-22 | P1 |
| F-SEC-08 | Immutable, hash-chained audit log with integrity verification indicator | M | NFR-12 | P2 |
| F-SEC-09 | End-to-end auditable trail: determination → disposition → approval → drawing incorporation (target 100% coverage) | M | NFR-12, K7 | P2 |
| F-SEC-10 | Audit filtering by user, date range, action type and component ID | P | Dashboard spec | P2 |
| F-SEC-11 | Zero-trust posture — mTLS between microservices | P | Annexure 2 §5.8 | P3 |
| F-SEC-12 | No telemetry transmitted outside the deployment environment; optional analytics fully disableable | M | NFR-02 | P2 |
| F-SEC-13 | Data sovereignty — no component routes, stores, processes or is controlled from a land-border country; full country-of-origin disclosure for every component | M | NFR-02 | P1 |
| F-SEC-14 | Compliance with GoI / CERT-In cybersecurity guidelines | M | NFR-03 | P3 |
| F-SEC-15 | Protection of licensed class-rule content per licensing terms | M | NFR-03 | P2 |
| F-SEC-16 | All data classified and retained within shipyard infrastructure; no external transmission | M | Data handling | P1 |
| F-SEC-17 | Software Bill of Materials (SBOM) delivered with full open-source licence inventory | M | Phase 3 deliverable | P3 |
| F-SEC-18 | Optional biometric / smart-card RBAC reader support | P | Hardware spec | P3 |

---

### 22.19 Deployment, Air-Gap & Operations (`OPS`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-OPS-01 | Fully on-premise deployment with air-gapped/offline operation — no internet dependency at install-time or run-time | M | NFR-01, FCM-26 | P0/P1 |
| F-OPS-02 | Containerised deployment (Docker-Compose for standard tier; Kubernetes manifests for enterprise tier) | P | D-06 | P2 |
| F-OPS-03 | Self-contained offline bundle — container images exported as `.tar` archives, loaded on-premise with no registry access | P | Air-gap package | P3 |
| F-OPS-04 | Bundled private local container registry for Kubernetes environments | P | Air-gap package | P3 |
| F-OPS-05 | All third-party dependencies bundled offline with telemetry disabled | M | NFR-01, NFR-02 | P3 |
| F-OPS-06 | Signed offline update packages for software and rule catalogs, with cryptographic integrity verification before install | M | NFR-09 | P3 |
| F-OPS-07 | Graceful GPU-optional operation — full deterministic core (compliance, CAD-BOM sync, dependency analysis, drawing management) functional with no GPU present | P | Air-gap package | P2 |
| F-OPS-08 | Modular deployment across development, pilot and production environments | P | Concept Note §4.2 | P2 |
| F-OPS-09 | Object storage for CAD files, simulation results and versioned model artefacts | P | Concept Note §4.2 | P1 |
| F-OPS-10 | Backup, recovery and archival procedures for engineering and audit data | P | Concept Note §4.3 | P3 |
| F-OPS-11 | High-availability configuration path for enterprise/full-ship scale rollout | P | Hardware spec | P3 |
| F-OPS-12 | Documented tiered hardware specification (Dev/Test, Recommended ~10,000-node, Enterprise full-ship) | M | Questionnaire §11 | P1 |

---

### 22.20 Model Lifecycle & MLOps (`MLO`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-MLO-01 | All model training and fine-tuning performed inside MDL's secure on-premise infrastructure; no production data leaves the shipyard | M | NFR-02 | P2 |
| F-MLO-02 | Controlled training data pipeline from historical CAD–BOM reconciliation records, ECR/ECO, revision history, approved BOM modifications, compliance review outcomes and validated engineer feedback | P | Questionnaire §7.8 | P2 |
| F-MLO-03 | Data splitting discipline — 70/15/15 train/validation/test with same-project revision histories kept unsplit to prevent leakage | P | Questionnaire §7.8 | P2 |
| F-MLO-04 | 5-fold cross-validation and hyperparameter optimisation (grid search / Bayesian) | P | Questionnaire §7.8 | P2 |
| F-MLO-05 | Limited-data strategies — transfer learning, synthetic rule/design variation datasets, geometric and metadata augmentation, few-shot learning for new equipment categories | P | Questionnaire §7.8 | P2 |
| F-MLO-06 | Active learning from engineer-reviewed corrections to prioritise future training samples | P | Questionnaire §7.8 | P3 |
| F-MLO-07 | Model versioning with full traceability of training data, parameters, evaluation metrics and approval records | M | NFR-07 | P2 |
| F-MLO-08 | Independent validation, regression testing, bias assessment and engineering review before any model deployment | P | Questionnaire §7.8 | P2 |
| F-MLO-09 | **No online or autonomous learning in production** — updates only through controlled offline retraining plus formal engineering approval | M | NFR-04 | P2 |
| F-MLO-10 | Per-ship-class model retraining pipeline delivered in handover documentation; cross-class generalisation not assumed | P | D-09 | P3 |
| F-MLO-11 | Continuous performance monitoring dashboard — precision, recall, F1, false-positive rate, false-negative rate, mean processing time | P | Questionnaire §7.5 | P2 |

---

### 22.21 Administration & Configuration (`ADM`)

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-ADM-01 | User and role management console | M | FR-24 | P1 |
| F-ADM-02 | Rule catalog editor with SME sign-off gating | P | Concept Note §2.1 | P2 |
| F-ADM-03 | Tolerance and threshold configuration UI (global / discipline / equipment type / component category / parameter) | M | NFR-10 | P2 |
| F-ADM-04 | Propagation parameter configuration — depth limit, decay λ, pruning threshold, edge weights | P | D-03 | P2 |
| F-ADM-05 | Confidence threshold configuration for auto-confirm and manual-review routing | P | D-09 | P2 |
| F-ADM-06 | Connector/adapter configuration for PLM, ERP and CAD endpoints | D | FR-26 | P2 |
| F-ADM-07 | Job queue administration — monitor, retry, cancel long-running tasks | P | D-12 | P2 |
| F-ADM-08 | Audit trail administration and retention configuration | P | Concept Note §2.1 | P2 |
| F-ADM-09 | Offline update installation workflow with package signature verification | M | NFR-09 | P3 |
| F-ADM-10 | Modular, documented and shipyard-supportable configuration with no vendor code changes required for routine changes | M | NFR-10 | P3 |

---

### 22.22 Performance & Quality Targets (`PRF`)

These are acceptance-gating characteristics, not optional.

| ID | Target | Priority | Trace |
|---|---|---|---|
| F-PRF-01 | CAD–BOM match **precision ≥ 90%** on pilot validation datasets | M | K5, D-14 |
| F-PRF-02 | CAD–BOM match **recall ≥ 90%** on pilot validation datasets | M | K5, D-14 |
| F-PRF-03 | Compliance validation **agreement with SME ≥ 85%** | M | K1, D-14 |
| F-PRF-04 | **Zero critical compliance false negatives** within validated rule scope | M | K1, D-14 |
| F-PRF-05 | Citation correctness / traceability to authoritative clauses at jointly agreed high threshold | M | K2 |
| F-PRF-06 | Assisted CAD–BOM validation agreement with SME ≥ 90% | P | Concept Note §3.6 |
| F-PRF-07 | Intelligent discrepancy prioritisation accuracy ≥ 85% vs SME-assessed criticality | P | Concept Note §3.6 |
| F-PRF-08 | Optimisation recommendation relevance ≥ 80% positive reviewer evaluation | P | Concept Note §3.6 |
| F-PRF-09 | Explainability & traceability coverage = 100% of analytical outputs | M | NFR-07 |
| F-PRF-10 | Knowledge graph completeness ≥ 95% of BOM line items with ≥1 dependency edge before go-live | P | Concept Note §3.5 |
| F-PRF-11 | Change impact analysis response in seconds for standard subsystem propagation | M | K6, NFR-05 |
| F-PRF-12 | Compliance delta validation completing within minutes for isolated modifications | M | NFR-05 |
| F-PRF-13 | Full baseline compliance evaluation within operationally practical review timelines | M | NFR-05 |
| F-PRF-14 | Measurable reduction in manual compliance-checking man-hours vs baseline | M | K3 |
| F-PRF-15 | Measurable reduction in change-propagation errors/rework against the ~25% post-contract-change baseline | M | K4 |
| F-PRF-16 | 100% auditable trail from determination → approval → drawing incorporation | M | K7 |
| F-PRF-17 | Validation cycle reduction from weeks to hours (programme-level objective) | P | Executive summary |

---

### 22.23 Testing, Validation & Documentation Deliverables (`DOC`)

| ID | Deliverable | Priority | Trace | Phase |
|---|---|---|---|---|
| F-DOC-01 | Software Requirement Specification (SRS) | P | D1 | P1 |
| F-DOC-02 | Solution Architecture Document with architecture and data-flow diagrams | P | D1 | P1 |
| F-DOC-03 | Project Management Plan, Stakeholder Matrix, Data Requirement Matrix | P | D1 | P1 |
| F-DOC-04 | Security Requirement Specification | P | D1 | P1 |
| F-DOC-05 | Capability Demonstration Report, demonstration video, technical feasibility assessment | P | Phase 0 | P0 |
| F-DOC-06 | Unit, integration, functional, security and performance test suites with coverage targets | P | Concept Note §6.4 | P2 |
| F-DOC-07 | Rule catalog validation fixtures and regression suite | P | Concept Note §6.4 | P1 |
| F-DOC-08 | Air-gapped operational verification test evidence | M | NFR-01 | P3 |
| F-DOC-09 | RBAC and audit-trail verification test evidence | M | FR-24, FR-25 | P3 |
| F-DOC-10 | Validation & Benchmarking Report with accuracy metrics and SME sign-off | P | D-07, D-14 | P2 |
| F-DOC-11 | UAT plan, execution records and sign-off by authorised MDL personnel | M | Acceptance criteria | P3 |
| F-DOC-12 | Administrator Manual | M | Phase 3 | P3 |
| F-DOC-13 | User Manual | M | Phase 3 | P3 |
| F-DOC-14 | Field Operations Manual (FOM) including rule-update and model-retraining procedures | P | D-07 | P3 |
| F-DOC-15 | API / interface specifications (OpenAPI 3.0) | P | D-05 | P2 |
| F-DOC-16 | Deployment, recovery and maintenance runbooks | P | Air-gap package | P3 |
| F-DOC-17 | Administrator and user training delivery plus training report | M | Phase 3 | P3 |
| F-DOC-18 | Source code handover | P | Phase 5 | P3 |
| F-DOC-19 | Operational Readiness Report and Project Closure Report | P | D7 | P3 |
| F-DOC-20 | Support plan for post-deployment operation | M | Phase 3 | P3 |

---

### 22.24 Conditional Scope — pending MDL decision (`CND`)

Not committed. These features are in or out depending on directions still to come from MDL. They are listed with IDs so that if MDL confirms them, they slot into the plan without renumbering, and so that effort and schedule impact can be quoted against a defined item rather than estimated from scratch.

#### 22.24.1 As-installed / as-built registration — **not finalised**

| ID | Feature | Priority | Trace | Phase |
|---|---|---|---|---|
| F-CND-01 | Ingest as-installed point cloud data — E57, LAS, PTS | C | FCM-3 | TBD |
| F-CND-02 | Ingest photographs / photogrammetry outputs of installation | C | FCM-4 | TBD |
| F-CND-03 | Pre-processing of point cloud and imagery (denoise, decimate, segment) | C | Questionnaire §6.4 | TBD |
| F-CND-04 | Registration / alignment of as-installed data to the ship design coordinate system using survey reference points or common geometric features | C | FCM-5 | TBD |
| F-CND-05 | As-built vs as-designed deviation comparison against the Digital Twin | C | Questionnaire §6.4 | TBD |
| F-CND-06 | Visual overlay of as-installed data against design geometry | C | FCM-16 | TBD |

**Impact if confirmed:** this brings the already-disclosed CV/3D stack (Open3D, PDAL, VTK, OpenCV, YOLOv11, SAM 2) into active use, and would also resolve the disclosure-vs-usage gap noted for those components. Modular architecture means it integrates without changes to the core platform, but it is a material addition to a 12-month schedule and needs its own scope, cost and timeline agreement before commitment.

**Impact if declined:** FCM rows 3–5 stand as "NO", and the CV/3D components should be reviewed for removal from the §8.2 disclosure so the platform is not claiming capability it does not use.

#### 22.24.2 Drawing format coverage — **awaiting MDL direction**

Working assumption, to be confirmed and revised per MDL's final direction on drawing formats and toolchain:

| Format | Working assumption | Confirmation needed |
|---|---|---|
| DXF | Full read/write — title block update, revision cloud generation | Confirm DXF is an accepted production drawing exchange format at MDL |
| PDF | Read plus stamped revision annotation overlay; no source edit | Confirm annotation-overlay output is acceptable for released drawings |
| DWG | Read/ingest assumed; **write support not yet scoped** | Confirm whether DWG write-back is required, and to which DWG version |
| CATIA `.CATDrawing`, NX `.prt` | Not edited directly; re-export triggered via CAD-system webhook | Confirm re-export path is workable within MDL's CAD licensing and workflow |
| TIFF (scanned) | Read plus OCR only | Confirm scanned drawing volume and whether output back to TIFF is needed |

Features F-DRW-06 through F-DRW-09 and F-DRW-13 are written against the working assumption above and will be revised once MDL direction is received. F-ING-05 (2D ingestion) is unaffected — ingestion coverage is committed regardless of which write paths are confirmed.

---

### 22.25 Appendix A — SoW Functional Requirement Coverage Map

| SoW FR | Requirement | Priority | AURORA features |
|---|---|---|---|
| FR-01 | Ingest detail design parameters | M | F-ING-01 |
| FR-02 | Ingest 3D CAD models | M | F-ING-02, F-ING-03, F-ING-09–13 |
| FR-03 | Ingest/parse BOM | M | F-ING-04, F-INT-09 |
| FR-04 | Ingest & structure rules incl. OCR | M | F-ING-06, F-ING-07, F-RKB-07 |
| FR-05 | Searchable versioned rule knowledge base | M | F-RKB-01, F-RKB-02, F-RKB-10 |
| FR-06 | Automatic compliance check | M | F-CMP-01, F-CMP-05 |
| FR-07 | Flag non-compliance with clause citation | M | F-CMP-03, F-XAI-01 |
| FR-08 | Design-optimization suggestions | D | F-CMP-18, F-OPT-01–11 |
| FR-09 | Confidence score per output | M | F-CMP-14, F-SYN-09, F-XAI-04 |
| FR-10 | Predict cross-discipline downstream impact | M | F-IMP-01–09 |
| FR-11 | Flag structural re-analysis / weight redistribution | M | F-IMP-10, F-IMP-11 |
| FR-12 | Flag re-qualification / testing & trials | M | F-IMP-12 |
| FR-13 | 3D↔BOM consistency check | M | F-SYN-01 |
| FR-14 | Detect 3D–BOM mismatches | M | F-SYN-12–18 |
| FR-15 | Traceability parameter↔rule↔BOM↔model | M | F-DTC-10, F-DRW-15 |
| FR-16 | Incorporate design into basic drawings | M | F-DRW-01 |
| FR-17 | Manage revisions/versions | M | F-CFG-01–03, F-DRW-10 |
| FR-18 | Incorporate approved revision into production drawings | M | F-DRW-02, F-DRW-12 |
| FR-19 | Review & approval workflow with disposition | M | F-WKF-01, F-WKF-09 |
| FR-20 | Explainability with source citations | M | F-XAI-01–03, F-GAI-10 |
| FR-21 | Compliance / impact / BOM-sync reports | M | F-RPT-01–07 |
| FR-22 | Dashboards / analytics | D | F-DSH-01–11 |
| FR-23 | Export to PDF and interchange formats | M | F-RPT-10, F-RPT-11 |
| FR-24 | Role-based user & access management | M | F-SEC-01, F-SEC-02, F-ADM-01 |
| FR-25 | Complete audit trail | M | F-SEC-07–10 |
| FR-26 | REST API for PLM/CAD/ERP integration | D | F-INT-01–07 |

### 22.26 Appendix B — SoW Non-Functional Requirement Coverage Map

| SoW NFR | Category | AURORA features |
|---|---|---|
| NFR-01 | Deployment (on-prem, air-gapped) | F-OPS-01–06, F-GAI-02 |
| NFR-02 | Data sovereignty | F-SEC-12, F-SEC-13, F-MLO-01 |
| NFR-03 | Security | F-SEC-03–06, F-SEC-14, F-SEC-15 |
| NFR-04 | Trustworthiness (grounded, cited, no hallucination) | F-XAI-01, F-XAI-07, F-GAI-10, F-GAI-11, F-MLO-09 |
| NFR-05 | Performance | F-ING-18, F-IMP-17, F-PRF-11–13 |
| NFR-06 | Scalability | F-DTC-11, F-INT-11 |
| NFR-07 | Explainability & traceability | F-XAI-02, F-XAI-03, F-MLO-07, F-PRF-09 |
| NFR-08 | Usability | F-DSH-12–15 |
| NFR-09 | Data currency (rule updates) | F-RKB-10–13, F-OPS-06, F-ADM-09 |
| NFR-10 | Maintainability | F-RKB-11, F-RKB-16, F-ADM-03, F-ADM-10 |
| NFR-11 | Interoperability | F-INT-03–05, F-INT-08 |
| NFR-12 | Auditability | F-SEC-08, F-SEC-09, F-CFG-11, F-PRF-16 |
-e 
---

## 23. UI/UX Architecture

### 23.1 Application shape

React + TypeScript single-page application, built as a static bundle, served from Nginx on-premise. All assets bundled at deployment time — **no browser dependency on any external resource**. Session management via on-premise LDAP/AD; JWT for API auth.

### 23.2 Navigation structure

```
AURORA
├── System Health & Status          (landing)
├── Impact Analysis
├── CAD–BOM Synchronisation
├── Compliance Validation
├── Drawing Synchronisation
├── Classification Society Workflow
├── Design Optimisation
├── Knowledge Graph Coverage
├── Analytics
├── Audit Trail
└── Administration                  (Admin role only)
    ├── Users & Roles
    ├── Rule Catalog
    ├── Tolerances & Thresholds
    ├── Connectors
    ├── Job Queue
    └── Offline Updates
```

Panels visible per role. The role-based interface hides controls the user cannot action, reducing operator error and cognitive load.

### 23.3 Screen specifications

| Panel | Contents |
|---|---|
| **System Health & Status** | Engine status indicators (Graph, Compliance, CAD–BOM Sync, Optimisation); last sync timestamp per data source (CAD, BOM, PLM); active job queue with running/queued/failed state; data freshness alerts |
| **Impact Analysis** | Change request input form (component ID, change type, magnitude); interactive propagation graph, filterable by system/deck; ranked impacted component list with impact scores and propagation paths; risk category badge per component; export PDF/JSON |
| **CAD–BOM Synchronisation** | Discrepancy summary table by type with counts; per-discrepancy drill-down showing CAD value vs BOM value, delta, per-signal scores and confidence; filter by system/deck/severity; bulk actions (accept match / flag for review / escalate); sync history log |
| **Compliance Validation** | Component-level PASS/FAIL/WARNING grid per rule; rule citation on every finding; change-triggered findings shown separately from baseline; multi-society conflict flags with conservative value applied; export submission package |
| **Drawing Synchronisation** | Drawing status table (CURRENT/STALE/PENDING_APPROVAL/READY_FOR_PRODUCTION); per-drawing diff view with changed attributes highlighted; revision cloud preview for DXF; approval controls (Approve / Reject / Request Revision); production release queue with one-click bundle download |
| **Classification Society Workflow** | Active submission tracker (date, society, status); society query inbox linked to component IDs; query response editor with mandatory justification; re-submission readiness checker; approval cycle history per package |
| **Design Optimisation** | Pareto front scatter plot (weight vs cost vs compliance); solution comparison table for side-by-side trade-off; parameter sensitivity chart (SHAP); export selected solution as recommendation report |
| **Knowledge Graph Coverage** | Real-time completeness metrics; isolated-node list for SME review |
| **Analytics** | Change volume, compliance status trend, impact statistics |
| **Audit Trail** | Immutable log of user actions, engine decisions and approval events; filters by user, date range, action type, component ID; hash-chain integrity indicator; export |

### 23.4 Usability provisions (design commitments)

- Role-based interface hides unnecessary controls.
- Change-triggered findings displayed separately from baseline findings to prevent information overload.
- **All compliance findings cite rule ID, actual value and allowable limit in plain engineering units — never an abstract score.**
- Interactive dependency graph with colour-coded severity (CRITICAL red / HIGH orange / MEDIUM amber / LOW green), filterable by ship system or deck.
- Match confidence scores displayed alongside every CAD–BOM match, for transparent engineer oversight.
- Mandatory engineer review checkpoint before any approval action — no autonomous approvals.
- One-click PDF export auto-named with `change_id` and timestamp, for programme review boards.
- All overrides recorded with mandatory justification text in the immutable audit trail.
- Fully on-premise; no internet required.

### 23.5 Input specifications

| Input | Mode |
|---|---|
| CAD model | File upload, PLM fetch, or CAD on-save webhook |
| BOM | ERP/PLM sync, file upload (CSV/XML/XLSX) |
| Drawing | File upload, PLM drawing vault, or folder watch |
| Rule document | Admin upload → parse → SME review → activate |
| Change request | Dashboard form: component ID, change type, magnitude |
| Society query | Structured JSON import, or manual entry |
| Engineer disposition | Approve / Reject / Refer + justification text |
| Configuration | Admin UI (tolerances, thresholds, weights, roles) |

### 23.6 Output specifications

| Output | Format |
|---|---|
| Compliance report | PDF, JSON |
| Impact assessment report | PDF, JSON |
| CAD–BOM reconciliation report | PDF, CSV, JSON |
| Classification submission package | PDF bundle + structured metadata |
| Design recommendation report | PDF |
| Drawing revision package | DXF/PDF + revision log |
| Production release bundle | Zip of approved drawings + BOM state + compliance record |
| Audit export | CSV, JSON |

Report content standard: deviation description; affected components and systems; root dependency path; compliance impact; recommended corrective actions; associated revision information; severity classification; engineering coordinates and subsystem references where applicable; rule/standard references; confidence.

### 23.7 Notifications

> **Not yet defined.** Notification channels (in-app, email via on-premise SMTP, none), triggers, escalation rules, digest cadence. **Trigger:** Phase 2 (D5) — dependent on MDL confirming whether an internal SMTP relay is available inside the air gap.

Known requirement: data freshness alerts appear on the System Health panel.

---

## 24. Error Handling, Logging & Observability

### 24.1 Error handling philosophy

**Never fail silently on engineering data.** A missing dependency, unresolved reference or unparseable component is a finding, not an exception to swallow. The system continues on validated data and explicitly flags what it could not process, with the confidence limitation stated.

### 24.2 Exception categories

| Category | Handling |
|---|---|
| Unsupported CAD format | Flag; attempt fallback bridge; report as ingestion finding |
| Degenerate geometry | Attempt shape healing; if unrecoverable, flag component as unprocessable with reason |
| Missing BOM attribute | Continue; flag attribute as unavailable; degrade affected signal in match scoring |
| Unresolved component reference | Flag as isolated/unlinked; surface for SME review |
| Rule with unparseable conditional expression | Rule does not activate; flagged to Admin; never silently skipped |
| Simulation reference missing for a LOAD_CASE rule | Rule evaluation returns "insufficient data", not PASS |
| Connector unreachable | Fall back to file-system path; surface staleness alert |
| Job failure | Surfaced in job queue with error log; retryable |
| Low retrieval confidence (GenAI) | Return "Insufficient evidence" — never speculate |

**Critical principle:** a rule that cannot be evaluated must never return PASS. Absence of evidence is not evidence of compliance.

### 24.3 Logging

| Log type | Store | Retention |
|---|---|---|
| Audit trail (user actions, engine decisions, approvals) | PostgreSQL, hash-chained | Indefinite — regulatory |
| Application logs | Local | *TBD* |
| Security logs | Local | *TBD* |
| Job/task logs | Local, surfaced in dashboard | *TBD* |

All logging is local. No telemetry leaves the deployment environment.

### 24.4 Monitoring & observability

- Engine status indicators per engine.
- Job queue state (running / queued / failed).
- Data freshness per source.
- Graph completeness coverage metric.
- Model performance validation dashboard (precision, recall, F1, FPR, FNR, mean processing time).
- Hash-chain integrity indicator.

### 24.5 Alerts

| Alert | Condition |
|---|---|
| Data freshness | Source not synced within configured window |
| Job failure | Any Celery task failure |
| Engine down | Engine health check fails |
| Graph coverage below gate | <95% BOM items with ≥1 edge |
| Audit chain integrity | Hash chain verification failure |
| Critical compliance finding | Any CRITICAL severity FAIL |

> **Not yet defined.** Alert delivery mechanism and thresholds. **Trigger:** Phase 2, alongside §23.7.

---

## 25. Performance, Scalability, Availability & Continuity

### 25.1 Performance requirements

| Workload | Target |
|---|---|
| Change impact analysis (standard subsystem) | Seconds |
| Compliance delta validation (isolated modification) | Minutes |
| Full baseline compliance evaluation (full vessel) | Within operationally practical engineering review timelines |
| CAD assembly ingestion | Benchmark against representative large-scale vessel assemblies on the reference configuration |
| Dashboard response | Responsive under standard engineering review workflows |
| Concurrent users | Multi-user support under the recommended deployment configuration |
| Optimisation workflow | Accelerated under GPU-enabled deployment where available |

> **Not yet defined.** Numeric response-time SLAs. These are deliberately unquantified pending pilot benchmarking on MDL data — publishing a number before measuring on real assemblies would be a guess. **Trigger:** Phase 1 pilot benchmarking; formalise in D6.

### 25.2 Scalability

- Modular service-oriented architecture; independent services for CAD parsing, BOM sync, compliance validation, optimisation and reporting execute in parallel.
- Graph-scoped analysis operates only on affected portions of the design, not the complete model — this is what makes full-ship scale tractable.
- Weighted, depth-limited traversal keeps propagation bounded even in highly interconnected systems.
- Scales from individual subsystems → complete ship platforms → multiple concurrent projects **without architectural redesign** (NFR-06).
- Target scale for the budgeted tier: ~10,000 component nodes. Enterprise tier addresses full-ship, multi-project scale.

### 25.3 Availability & reliability

> **Not yet defined.** Uptime targets, HA topology, failover behaviour, RTO/RPO. HA configuration exists at the enterprise hardware tier (PostgreSQL replicated, ArcadeDB clustered, Redis Sentinel, MinIO distributed) but no availability SLA has been agreed. **Trigger:** Phase 0 discussion with MDL IT; formalise before Phase 3.

Reliability commitments that do exist:
- Deterministic engines produce identical outputs for identical inputs — reproducibility is a reliability property here.
- Graceful degradation: no GPU, no training data, no PLM connectivity — core capability continues in every case.

### 25.4 Backup strategy

Backup/tape storage unit is specified in the recommended hardware tier, primarily for offline update packages. Object storage holds versioned CAD, simulation and model artefacts. Git holds versioned engineering artefacts and baselines.

> **Not yet defined.** Backup schedule, scope, medium rotation, restore verification cadence. **Trigger:** Phase 3 operational readiness.

### 25.5 Disaster recovery & business continuity

> **Not yet defined.** DR site, recovery procedures, RTO/RPO targets, failover drill schedule. **Trigger:** Phase 3; must be agreed with MDL IT.

Continuity fallback that exists by design: **the existing manual process remains available throughout.** AURORA does not replace any system, so its unavailability degrades productivity but does not stop ship design.

---

## 26. Engineering Practice

### 26.1 Versioning strategy

| Artefact | Scheme |
|---|---|
| Application | *TBD — semantic versioning proposed* |
| Rule catalog | Versioned with `effective_date`; superseded rules retained |
| ML models | Versioned artefacts with full lineage (training data, parameters, metrics, approval) |
| Engineering data | Per-object `version_history` with delta hash; Git-backed baselines |
| Drawings | Rev N → Rev N+1 with change delta logged |
| Baselines | Tagged: Contract Design / Basic Design / Class Submission / Class Approved / Production Release |
| API | *TBD* |

### 26.2 Git branching strategy

> **Not yet defined.** **Trigger:** Phase 1 development start. Note that a local Git instance also runs *inside* the air-gapped deployment for engineering artefact versioning (§16.3) — that is a separate concern from the development repository and the two must not be conflated.

### 26.3 Repository structure

> **Not yet defined.** **Trigger:** Phase 1 development start.

### 26.4 Coding & development standards

> **Not yet defined.** **Trigger:** Phase 1 development start.

Constraints that will shape them: Python 3.12 and TypeScript 5.8; every engineering output must carry an evidence chain (AP-02), so evidence construction cannot be optional in any engine interface; no component may make an outbound network call (AP-04), which should be enforced by lint/CI check, not by convention.

---

## 27. Testing Strategy

### 27.1 Test architecture

| Level | Scope |
|---|---|
| Unit | Individual functions, rule evaluators, signal calculators, graph operations |
| Integration | Engine-to-engine flows; ingestion → registry → graph → compliance |
| System | Full workflow end-to-end across all 8 operational stages |
| Regression | Triggered by any rule catalog or algorithm change |
| Performance | Benchmarking against representative large-scale assemblies |
| Security | Penetration, access control, encryption verification |
| Air-gap | Verification of zero external connectivity under operation |
| Acceptance (UAT) | MDL engineering personnel, representative historical scenarios |

### 27.2 Rule test fixtures

Every digitised rule ships with **known-good and known-bad fixtures**. A rule without fixtures does not activate. This is the primary defence against R-02 (false compliance passes from incomplete rule digitisation) and the mechanism by which PT-04 (zero critical false negatives) is made testable rather than aspirational.

### 27.3 Trial phasing (end-user trials)

| Phase | Purpose | Activities |
|---|---|---|
| **A — Controlled Validation Trial** | Validate core engineering workflows on representative historical datasets | CAD–BOM validation, compliance checks, dependency propagation verification |
| **B — End-User Acceptance Trial** | Validate operational usability and workflow alignment with MDL engineering teams | Dashboard workflows, revision management, approval workflows, discrepancy review |
| **C — Production Readiness Verification** | Validate deployment readiness and governance controls | Air-gap verification, audit validation, RBAC verification, deployment readiness review |

### 27.4 Representative validation scenarios

| Scenario | Objective |
|---|---|
| CAD–BOM discrepancy detection | Verify identification of missing, duplicate or inconsistent records |
| Engineering change impact analysis | Validate dependency-aware propagation across affected subsystems |
| Multi-society compliance validation | Confirm detection and traceability of compliance findings |
| Drawing revision synchronisation | Verify propagation of approved revisions into associated drawings |
| Classification submission workflow | Validate generation and traceability of submission-ready packages |
| RBAC & approval workflow | Verify controlled access and approval hierarchy enforcement |
| Audit trail verification | Confirm traceability and integrity of workflow records |
| Air-gapped operational verification | Validate complete offline capability with no external connectivity |

Pilot execution targets **4 historical scenarios** provided by MDL.

### 27.5 Test data

Sourced from MDL historical engineering datasets (dependent on A-01). Supplemented by synthetic engineering datasets generated through controlled rule and design variations where historical volume is insufficient.

> **Not yet defined.** Specific test dataset inventory. **Trigger:** Phase 0 data audit.

### 27.6 Test coverage targets

Target unit and integration test coverage across core engineering modules; structured integration validation before pilot deployment; traceable regression validation following major engineering or rule-catalog updates.

> **Not yet defined.** Numeric coverage percentage. **Trigger:** Phase 1 development standards definition.

### 27.7 Test cases

> **Not yet defined.** Individual test case specifications. **Trigger:** Phase 1 onward, per module. Rule fixtures (§27.2) are the exception — those are defined per rule as rules are digitised.

---

## 28. CI/CD, Build, Release & Rollback

### 28.1 Build process

Containerised build producing Docker images; frontend built as a static bundle; images exported as `.tar` archives for air-gap delivery.

> **Not yet defined.** Build pipeline configuration, artefact registry (internal), signing process. **Trigger:** Phase 1 development start.

### 28.2 CI/CD pipeline

> **Not yet defined.** **Trigger:** Phase 1 development start.

Constraint to design for: the production target has **no network path from the CI environment**. The pipeline terminates at a signed offline bundle, not at a deployment. Deployment is a manual, controlled, air-gap-crossing operation.

### 28.3 Deployment process

1. Build and sign offline bundle.
2. Transfer across the air gap by approved physical medium.
3. Verify package signature and integrity on-premise.
4. `docker load` images; apply Docker-Compose or Kubernetes manifests.
5. Run migration (Alembic) and post-deploy verification.
6. Confirm zero outbound connectivity.

### 28.4 Release criteria

- All mandatory FRs for the phase implemented and tested.
- Regression suite green, including all rule fixtures.
- Security testing passed.
- Air-gap verification passed.
- Documentation updated.
- Review gate approval obtained (RG-1 → RG-4 as applicable).

### 28.5 Rollback strategy

> **Not yet defined.** **Trigger:** Phase 2. Must account for the air gap: rollback cannot pull a previous image from a registry, so the previous version's bundle must be retained on-premise. Database migration reversibility needs explicit design given engineering data must never be lost.

---

## 29. Change, Configuration, Issue & Defect Management

### 29.1 Engineering change control (the product's own domain)

Controlled change-management workflows with impact assessment prior to operational deployment. Every design change flows through the 8-stage workflow (§8.2) with mandatory human approval.

### 29.2 Project change control

> **Not yet defined.** Change request process, impact assessment procedure, approval authority for scope changes. **Trigger:** Contract award. Critical given the 20→12 month compression — scope changes must be governed tightly.

### 29.3 Configuration management

Version-controlled engineering artefacts, deployment packages and rule catalogs with traceable revision management. Rule catalog, model artefacts, container images and engineering baselines are all separately versioned.

### 29.4 Issue & defect management

Controlled defect tracking with severity-based resolution workflows. Resolution, mitigation or formally documented acceptance of identified critical defects is a precondition of operational acceptance.

> **Not yet defined.** Tracking tool, severity definitions, SLA per severity, triage cadence. **Trigger:** Phase 1 development start.

---

## 30. Technical Decisions & Architecture Decision Records

### 30.1 ADR index

| ADR | Decision | Status | §41.1 ref |
|---|---|---|---|
| ADR-01 | Deterministic-first architecture; ML excluded from compliance determination paths | Accepted | DL-01 |
| ADR-02 | ArcadeDB as graph database (over Neo4j) | Accepted | DL-02 |
| ADR-03 | Drools as deterministic rule engine | Accepted | DL-03 |
| ADR-04 | Multi-library ML approach; selection by empirical validation performance | Accepted | DL-04 |
| ADR-05 | GenAI/RAG layer classified non-core and deferrable | Accepted | DL-05 |
| ADR-06 | 12-month delivery plan (revised from 20) | Accepted | DL-06 |
| ADR-07 | Deterministic cold-start mode for CAD–BOM matching | Accepted | DL-07 |
| ADR-08 | Change-triggered delta compliance mode rather than full re-scan | Accepted | DL-08 |
| ADR-09 | Drawing modification limited to DXF write and PDF overlay; parametric CAD via re-export | Provisional — pending MDL direction | DL-09 |
| ADR-10 | No geometry write-back to CAD models | Provisional — pending MDL confirmation on T2 | DL-10 |

### 30.2 Key trade-offs

| Trade-off | Chosen | Given up | Rationale |
|---|---|---|---|
| Deterministic rules vs learned compliance model | Deterministic | Potential accuracy on ambiguous rules; adaptability | Citability and reproducibility are regulatory requirements. A model that cannot name the clause it applied is unusable for class submission |
| Conservative multi-path impact accumulation (max) vs averaged | Max across paths | Precision; more false positives | Under-reporting impact is the dangerous failure. Over-reporting costs review time; under-reporting costs rework |
| Delta compliance mode vs full re-scan every time | Delta (after baseline) | Simplicity; guaranteed total coverage each run | A full-system compliance dump on every change is operationally ignored. Change-scoped output is what makes T1 usable. Baseline scan requirement mitigates the coverage risk |
| Phased 30% rule coverage vs full coverage before go-live | Phased | Completeness at Phase 1 | Full digitisation of all society rule sets is not achievable in 12 months. Prioritising by severity and frequency delivers most of the value early. **The residual risk is that an undigitised rule is silently un-checkable** |
| ML confidence scoring vs pure deterministic matching | Both — ML optional over a deterministic base | Simplicity | Deterministic-only works from day one with zero data; ML adds accuracy when data exists. Neither is a single point of failure |
| Depth-limited traversal (6 hops) vs unbounded | Depth-limited | Discovery of very distant dependencies | Unbounded traversal on a dense graph returns everything, which is the same as returning nothing. Configurable per project |
| BOM-from-CAD update vs bidirectional geometry write-back | BOM-from-CAD + CAD re-export trigger | Full T2 literal compliance | Writing geometry into parametric CAD from outside the CAD system is fragile and risks corrupting the design authority's model. **This trade-off is unconfirmed with MDL — see R-11** |

### 30.3 Alternatives considered

| Area | Alternative | Why not chosen |
|---|---|---|
| Graph DB | Neo4j | ArcadeDB offers a broader feature set; also multi-model, avoiding a separate document store |
| Rule engine | Custom evaluator | Drools is mature, decouples rule authoring from code (NFR-09/10), and is already in the security disclosure |
| LLM as compliance engine | Prompt-based rule evaluation | Fails NFR-04 outright. Non-negotiable |
| Cloud deployment | Any hosted component | Fails NFR-01 and NFR-02 outright. Non-negotiable |
| Point cloud as-built verification | In-scope from the start | Outside PS-71's stated objectives; would consume Phase 1 capacity needed for core commitments. Retained as conditional |

### 30.4 Known limitations

Carried forward from §19.7 plus:

| # | Limitation |
|---|---|
| KL-01 | AURORA does not modify parametric CAD drawing files directly (CATIA `.CATDrawing`, NX `.prt`) — these require re-export from the CAD system |
| KL-02 | PDF drawings receive an annotation overlay only; the source PDF is not edited |
| KL-03 | DWG write support is not scoped |
| KL-04 | Compliance coverage is bounded by digitised rule coverage, targeted at ~30% (critical rules) in Phase 1 |
| KL-05 | The system prepares classification submission packages but cannot submit them |
| KL-06 | The system flags where FEA/CFD re-analysis is required but does not run solvers |
| KL-07 | Enterprise full-ship-scale hardware is outside the current budget band; the delivered system targets ~10,000-node scale |

### 30.5 Known issues

None — no code exists yet.

### 30.6 Technical debt

None accrued. Debt to watch for, given the 12-month compression: rule fixtures skipped under time pressure (this directly compromises PT-04); evidence-chain construction bolted on rather than built into engine interfaces; connector fallbacks left unimplemented because the primary integration happened to work in the pilot environment.

---
## 31. Roadmap, Timeline, Milestones & Deliverables

### 31.1 Delivery phases (SoW §11)

| Phase | Description | Key deliverables | Indicative acceptance |
|---|---|---|---|
| **Phase 0 — Capability Demonstration** | Small, time-boxed demonstration on a sample or existing product | Working demo of an automated clause-cited compliance check **or** a 3D–BOM mismatch detection; offline-capability evidence | Demonstrated technical maturity and directional fit |
| **Phase 1 — Pilot / MVP** | Limited scope: one discipline/system, subset of class rules, core compliance check + basic impact flags + 3D–BOM check | Deployed pilot on shipyard data; accuracy & citation report; workflow walk-through | Meets agreed pilot accuracy and workflow criteria |
| **Phase 2 — Full Development** | All disciplines, full rule coverage, cross-discipline impact prediction, 3D–BOM sync, revision workflow, integration | Full-featured system per FR-01–FR-26; documentation; training | Meets functional & non-functional requirements |
| **Phase 3 — Secure Deployment & Scale** | Air-gapped production deployment, full-project scale, handover & support | Production deployment; admin/user training; support plan; SBOM | Operational acceptance in secure environment |

### 31.2 12-month schedule

| Months | Milestone | Deliverable |
|---|---|---|
| Pre-start | — | Phase 0 Capability Demonstration |
| M0–M2 | **M1** | **D1** — Requirement Finalization & Solution Architecture |
| M2–M4 | **M2** | **D2** — Data Ingestion & Knowledge Base |
| M4–M6 | **M3** | **D3** — Pilot AI Platform |
| M6–M8 | **M4** | **D4** — Advanced AI Engine |
| M8–M10 | **M5** | **D5** — Enterprise Platform |
| M10–M11 | **M6** | **D6** — Testing & Validation |
| M11–M12 | **M7** | **D7** — Production Deployment & Project Closure |

**Month 0 = contract award date.** Not yet set.

### 31.3 Review gates

| Gate | Timing | Approval scope |
|---|---|---|
| **RG-1** | End M2 | Project scope, architecture and pilot success criteria |
| **RG-2** | End M6 | Pilot acceptance review |
| **RG-3** | End M10 | Full functional review and enterprise acceptance |
| **RG-4** | End M12 | Final acceptance and commissioning approval |

### 31.4 Work breakdown by deliverable

**Phase 0 — Capability Demonstration (pre-start)**
Activities: CAD model ingestion demo; engineering document ingestion demo; AI-assisted class rule compliance checking; automated clause citation; 3D–BOM synchronisation demo; sample compliance report generation; explainability demo; offline deployment demo.
Outputs: Capability Demonstration Report; demonstration video; technical feasibility assessment; demonstration feedback report.

**D1 — Requirement Finalization & Solution Architecture (M0–M2)**
Activities: kick-off with MDL; requirement elicitation workshops; review of existing design workflows; review of CAD and BOM management practices; identification of applicable classification rules, standards and regulations; definition of pilot scope; security requirement analysis; air-gapped deployment planning; SRS preparation; high-level architecture design; initial risk assessment.
Outputs: SRS; Solution Architecture Document; Project Management Plan; Stakeholder Matrix; Data Requirement Matrix; Security Requirement Specification.
Gate: **RG-1**.

**D2 — Data Ingestion & Knowledge Base (M2–M4)**
Activities: collection of CAD models, BOM data, engineering drawings, class rules and standards; OCR processing pipeline; metadata extraction; semantic indexing; knowledge base construction; version control framework.
Outputs: Engineering Knowledge Base; Data Ingestion Framework; Rule Repository; Document Processing Pipeline.

**D3 — Pilot AI Platform (M4–M6)**
Activities: compliance analysis engine; rule citation engine; engineering optimisation suggestions; 3D–BOM matching; mismatch detection; traceability framework; pilot dashboard; pilot reporting; internal validation.
Outputs: Pilot AI Platform; Compliance Analysis Module; 3D–BOM Synchronization Engine; pilot demonstration.
Gate: **RG-2**.

**D4 — Advanced AI Engine (M6–M8)**
Activities: multi-disciplinary rule engine; cross-discipline impact analysis; structural impact prediction; weight redistribution analysis; revision management; workflow engine; review & approval workflow; explainability framework.
Outputs: Advanced AI Engine; Change Impact Module; Revision Workflow; Review Dashboard.

**D5 — Enterprise Platform (M8–M10)**
Activities: PLM integration; CAD integration; ERP integration; REST APIs; RBAC; audit logging; analytics dashboard; PDF report generation; performance optimisation.
Outputs: Enterprise Platform; Integration Framework; Reporting Engine; Analytics Dashboard.
Gate: **RG-3**.

**D6 — Testing & Validation (M10–M11)**
Activities: functional testing; integration testing; security testing; air-gapped validation; user acceptance testing; performance benchmarking; cyber security validation; defect resolution.
Outputs: Testing Report; Validation Report; UAT Sign-Off; Security Compliance Report.

**D7 — Production Deployment & Project Closure (M11–M12)**
Activities: production deployment; air-gapped installation; administrator training; user training; documentation handover; operational readiness assessment; final demonstration; knowledge transfer; project closure.
Outputs: Production Deployment; Administrator Manual; User Manual; Training Report; Operational Readiness Report; Project Closure Report.
Gate: **RG-4**.

### 31.5 Product deliverable register (D-01 → D-15)

Distinct from the phase deliverables D1–D7. These are the product artefacts.

| ID | Deliverable | Type | Description |
|---|---|---|---|
| D-01 | Digital Twin Core | Data + Engine | Unified parametric model integrating CAD geometry, BOM metadata, simulation data and rule bindings per component |
| D-02 | Dependency Knowledge Graph | Database | Directed weighted graph encoding all inter-system dependencies with documented relationship taxonomy |
| D-03 | Impact Propagation Engine | Software Module | BFS/DFS traversal with exponential depth decay; ranked impact lists with propagation path explanations |
| D-04 | Decision Output Engine | Software Module | Consolidated engineer-facing report: compliance status, BOM sync errors, optimised design recommendations |
| D-05 | System Integration Package | APIs + Docs | REST API layer, PLM adapter stubs, CAD webhooks, full OpenAPI 3.0 specification |
| D-06 | Security & Deployment Package | Infrastructure | Docker-Compose / Kubernetes manifests for air-gapped on-premise deployment |
| D-07 | Validation & Acceptance Report | Document | End-to-end validation against real engineering scenarios; accuracy metrics; SME sign-off certificate |
| D-08 | CAD Parsing & Normalisation Engine | Software Module | Geometry features, assembly hierarchy, mass properties from STEP/IGES/SolidWorks via PythonOCC |
| D-09 | CAD-BOM Synchronisation Engine | Software Module | Multi-method matching with ML confidence scoring; structured discrepancy reports |
| D-10 | Multi-Society Rule Compliance Engine | Software Module | Deterministic rule evaluation against IRS/LR/DNV/BV/ABS with per-rule audit trail; baseline and change-triggered delta modes |
| D-11 | Design Optimisation Engine | Software Module | NSGA-II multi-objective optimisation; Pareto front output; sensitivity-analysis fallback |
| D-12 | AURORA Decision Intelligence Dashboard | Software Module | React + TypeScript on-premise web application across all engine outputs |
| D-13 | Drawing Synchronisation & Revision Engine | Software Module | Automated propagation of approved changes into production drawings; DXF/PDF handling; `DRAWING_STALE` detection; PLM vault targeting with folder-watch fallback |
| D-14 | Validation Benchmarking Report | Document | Accuracy report: CAD-BOM precision ≥90% / recall ≥90%; SME agreement ≥85%; zero critical false negatives; FP/FN analysis; SME sign-off |
| D-15 | Classification Society Submission Package | Module + Document | Structured approval packages for IRS/LR/DNV/BV/ABS; society query ingestion workflow; full submit → query → resolve → re-submit cycle |

### 31.6 Product roadmap beyond the contract

| Horizon | Content |
|---|---|
| Post-delivery | Expanded rule library coverage beyond Phase 2 scope; PLM/ERP integration refinement against MDL's live environment |
| Conditional | As-installed / point cloud verification (§6.4) if MDL confirms |
| Future enhancement | PyTorch FEA surrogate models, once simulation data volume justifies |
| Scale | Enterprise HA cluster, full-ship scale, multi-programme concurrency |
| Commercial | Cross-industry verticalisation — aerospace, energy, rail, heavy engineering, any regulated engineered product |

---

## 32. Team, Roles & Governance

### 32.1 Team structure

> **Not yet defined.** No staffing commitment ahead of award. **Trigger:** contract award.

Roles the plan implies and which must be filled: Delivery Lead; Architecture Lead; Rule/Domain Lead (naval engineering + classification rules); ML Lead; Integration Lead; Frontend Lead; DevOps/Security Lead; QA Lead.

**Note:** the bid scores Team Capability at 5 points and requires evidence. §33 records CDAC-Mumbai as a validation relationship, not a staffing one.

### 32.2 RACI matrix

> **Not yet defined.** **Trigger:** contract award, alongside §32.1.

### 32.3 Roles and responsibilities

> **Not yet defined.** **Trigger:** contract award.

### 32.4 Decision authority

| Decision type | Authority |
|---|---|
| Requirement interpretation | MDL — raise, do not resolve internally |
| Engineering approval within the product | Designated MDL personnel only. Non-negotiable, architecturally enforced |
| Rule activation | MDL SME sign-off required |
| Tolerances, thresholds, severity levels | Joint MDL–Arcaisys agreement |
| Technology selection | Arcaisys, subject to the §8.2 disclosure already submitted for security clearance |
| Scope change | MDL, via project change control (§29.2) |
| Phase gate progression | MDL programme authority (RG-1 → RG-4) |
| Final acceptance | MDL programme authority |

### 32.5 Approval workflow (project governance)

Milestone completion → deliverable submission → MDL review → review gate (RG-n) → approval → next phase. Operational deployment progresses only after completion of agreed acceptance activities and formal approval through MDL's engineering and programme governance processes.

### 32.6 Communication protocols & meeting cadence

> **Not yet defined.** **Trigger:** contract award; to be set at kick-off (D1).

Known fixed points: project kick-off meeting with MDL; requirement elicitation workshops; SME workshops for edge-weight calibration and rule validation; 2-day user training workshop; final demonstration.

---

## 33. External Dependencies, Third-Party Components & Licensing

### 33.1 Vendor & partner dependencies

| Party | Relationship | Status |
|---|---|---|
| MDL | Customer; data, SME, infrastructure and approval provider | Bid submitted, undecided |
| CDAC-Mumbai | Technical validation; senior faculty reviewed the solution | Informal. **Collaboration anticipated, not contracted.** Do not represent as a delivery partner without an agreement |
| Classification societies (IRS, LR, DNV, BV, ABS) | Rule content source; external approval authority | Indirect. Rule content is licensed to MDL, not to Arcaisys |

### 33.2 Third-party & open source components

Full inventory in §14.2, with declared alternatives in §14.3 and country of origin in §14.4.

### 33.3 Licence summary

| Licence | Components |
|---|---|
| MIT | React, FastAPI, SQLAlchemy, Alembic, Pydantic, Open3D, ONNX Runtime, spaCy |
| Apache 2.0 | TypeScript, OpenCV, SAM 2, Tesseract, HF Transformers, Sentence Transformers, all-mpnet-base-v2, Qdrant, **ArcadeDB**, **Drools**, Docker, Kubernetes |
| BSD | Uvicorn, PyTorch, Scikit-learn, PDAL, VTK |
| PSF | Python |
| PostgreSQL Licence | PostgreSQL |
| GPL | Ubuntu Server LTS |
| **AGPL-v3** | **YOLOv11** — the only copyleft component. Currently attached to no committed feature. See R-10 |
| **RSALv2 / SSPLv1** | **Redis 8** — not OSI open source. Valkey (BSD-3) is the identified alternative |
| Meta Llama 3.1 Community Licence | Llama 3.1 8B Instruct — non-core layer only |

> **Internal note.** The AGPL-v3 and RSAL/SSPL entries are the two licence positions that could draw scrutiny in a defence procurement review. Both have clean alternatives already declared. Resolving them is cheap now and expensive later.

### 33.4 SBOM

Software Bill of Materials is a **Phase 3 deliverable** and an explicit acceptance requirement.

> **Not yet defined.** Generated SBOM artefact. **Trigger:** Phase 3, before production deployment. Format should be CycloneDX or SPDX.

---

## 34. IP, Regulatory & Procurement

### 34.1 Intellectual property

Handled under the iDEX DRISHTI Challenge terms and the confidentiality/IP provisions of Annexure-II §1.4.

> **Not yet defined.** Specific IP ownership, licensing and background-IP positions. **Trigger:** contract negotiation on award. This must be settled before source code handover (a committed deliverable) is executed.

### 34.2 Patent considerations

> **Not yet defined.** No patent filing assessed. Candidate subject matter if pursued: the multi-signal CAD–BOM correspondence method with confidence gating, and the change-triggered delta compliance mode with attribute-delta-scoped rule selection. **Trigger:** post-award IP review.

### 34.3 Regulatory requirements

Covered in §18.6. Governing constraints: GoI procurement restrictions on land-border countries; CERT-In cybersecurity guidelines; data sovereignty; DPDP Act 2023.

### 34.4 Procurement requirements

- Compliance with the Order (Public Procurement No. 1), Department of Expenditure, Ministry of Finance — **confirmed compliant**.
- Registration with the Competent Authority where applicable.
- No software, model, hardware or cloud dependency routes, stores, processes or is controlled from a land-border country — **confirmed**.
- Full country-of-origin disclosure provided (§14.4).

---

## 35. Cost, Budget & Resources

> **Intentionally omitted from this document.**

The milestone payment schedule in the submitted bid was constructed against the 20-month plan and does not survive the compression to 12 months. Rather than carry stale figures, cost is excluded entirely from the SSoT. **No figure appearing in any earlier document should be treated as current.**

**Action required:** re-phase the milestone payment schedule against the 12-month plan (M1–M7 / D1–D7) before contract negotiation. Tracked as AI-02 in §43.3.

Hardware cost bands remain in §15.4 as *specification context*, not budget.

Resource requirements: see §32.1 (unstaffed pending award).

---

## 36. Operational Procedures

### 36.1 Deployment runbook

> **Not yet defined.** **Trigger:** Phase 3 (D7). Included in the air-gap deployment package as a committed deliverable.

Known structure: §28.3 outlines the deployment sequence.

### 36.2 Operations runbook / Field Operations Manual (FOM)

Committed deliverable. Must include:
- Quarterly rule catalog update process.
- Model retraining pipeline procedure.
- Offline update package installation and verification.
- Backup and recovery procedures.
- User and role administration.

> **Not yet defined.** Full FOM content. **Trigger:** Phase 3.

### 36.3 Troubleshooting guide

> **Not yet defined.** **Trigger:** Phase 3 (D7).

### 36.4 Incident response

Aligned with CERT-In guidelines for logging and incident response.

> **Not yet defined.** Incident classification, escalation path, MDL/Arcaisys responsibility split, response SLAs. **Trigger:** Phase 3; must be agreed with MDL IT and cybersecurity.

### 36.5 Maintenance procedures

Modular, documented and supportable within the shipyard (NFR-10). Rule catalog and thresholds are configurable without vendor code changes (NFR-09). Quarterly rule refresh process defined in the FOM.

### 36.6 Support procedures

Support plan is a Phase 3 committed deliverable.

> **Not yet defined.** Support model, hours, escalation, duration post-handover. **Trigger:** contract negotiation and Phase 3.

---

## 37. Documentation, Training & Onboarding

### 37.1 Documentation deliverables

| Document | Phase | Status |
|---|---|---|
| Software Requirement Specification | D1 | Not started |
| Solution Architecture Document | D1 | Not started |
| Project Management Plan | D1 | Not started |
| Stakeholder Matrix | D1 | Not started |
| Data Requirement Matrix | D1 | Not started |
| Security Requirement Specification | D1 | Not started |
| API specification (OpenAPI 3.0) | D5 | Not started |
| Testing Report / Validation Report | D6 | Not started |
| Security Compliance Report | D6 | Not started |
| UAT Sign-Off | D6 | Not started |
| Administrator Manual | D7 | Not started |
| User Manual | D7 | Not started |
| Field Operations Manual | D7 | Not started |
| Training Report | D7 | Not started |
| Operational Readiness Report | D7 | Not started |
| Project Closure Report | D7 | Not started |
| SBOM | D7 | Not started |
| Validation Benchmarking Report (D-14) | Phase 2 | Not started |
| Validation & Acceptance Report (D-07) | Phase 2/3 | Not started |

### 37.2 Documentation standards

Maintenance of architecture documentation, operational manuals, interface specifications and deployment records throughout the lifecycle, with documentation completeness tracked as a software quality metric.

> **Not yet defined.** Template, format and review standards. **Trigger:** Phase 1.

### 37.3 Training requirements

- Administrator training (Phase 3).
- User training (Phase 3), including a committed **2-day user training workshop**.
- Knowledge transfer and documentation handover at project closure.

System is required to be usable by design and configuration engineers **with minimal training** (NFR-08) — the training programme supplements a usable interface, it does not substitute for one.

### 37.4 Onboarding guide

> **Not yet defined.** **Trigger:** Phase 3, derived from the User Manual.

---

## 38. Glossary, Acronyms & Domain Terminology

### 38.1 Domain terminology

| Term | Meaning |
|---|---|
| **Class Rules** | Technical rules issued by a classification society governing ship design and construction |
| **Classification Society** | Body that sets and verifies technical standards for ships (e.g. IACS members) |
| **Standards / Regulations** | Applicable national and international technical standards and statutory regulations |
| **Contract Design** | The design stage at which the contract is agreed; changes after this point are the ~25% problem |
| **Detail Design** | The detailed engineering design derived from contract/basic design |
| **Basic Drawings** | Design drawings submitted to the classification society for approval |
| **Production Drawings** | Drawings issued to production, updated with class-approved revisions |
| **BOM** | Bill of Material — structured list of components, quantities and specifications |
| **Change Impact / Propagation** | Downstream effects of a design change across disciplines |
| **Knowledge Base** | Structured, searchable store of rules and standards used by the system |
| **Confidence Score** | A measure of the system's certainty in an output |
| **Explainability / Citation** | Showing the exact rule/BOM/model evidence behind an output |
| **Air-Gapped** | Isolated from external/public networks, including the internet |
| **Digital Twin** | The unified parametric representation of every ship component in AURORA |
| **Delta mode** | Change-triggered compliance evaluation limited to rules affected by changed attributes |
| **Cold start** | Operating mode with no historical training data; deterministic matching only |
| **Baseline scan** | Full-system compliance evaluation; prerequisite for delta mode |
| **Pareto front** | The set of non-dominated design alternatives in multi-objective optimisation |
| **Revision cloud** | Drawing annotation marking a changed region |

### 38.2 Acronyms

| Acronym | Expansion |
|---|---|
| ABS | American Bureau of Shipping |
| AD | Active Directory |
| ADR | Architecture Decision Record |
| AGPL | Affero General Public License |
| API | Application Programming Interface |
| ASGI | Asynchronous Server Gateway Interface |
| AURORA | Automated Unified Reasoning and Optimization Architecture |
| BFS | Breadth-First Search |
| BOM | Bill of Materials |
| BREP | Boundary Representation |
| BRepBndLib | OpenCascade module for axis-aligned bounding boxes |
| BRepGProp | OpenCascade module for geometric properties (mass, inertia, surface area) |
| BV | Bureau Veritas |
| CAD | Computer-Aided Design |
| CATIA | Computer Aided Three-dimensional Interactive Application (Dassault Systèmes) |
| CDAC | Centre for Development of Advanced Computing |
| Celery | Distributed task queue for Python |
| CERT-In | Indian Computer Emergency Response Team |
| CFD | Computational Fluid Dynamics |
| CoG / CoM | Centre of Gravity / Centre of Mass |
| CSV | Comma-Separated Values |
| DNV | Det Norske Veritas |
| DPDP | Digital Personal Data Protection (Act, 2023) |
| DXF / DWG | Drawing Exchange Format / AutoCAD Drawing |
| ECR / ECO | Engineering Change Request / Order |
| ERP | Enterprise Resource Planning |
| FastAPI | Python web framework for REST APIs |
| FEA | Finite Element Analysis |
| FOM | Field Operations Manual |
| FR / NFR | Functional Requirement / Non-Functional Requirement |
| GoI | Government of India |
| HITL | Human In The Loop |
| HVAC | Heating, Ventilation and Air Conditioning |
| IACS | International Association of Classification Societies |
| iDEX | Innovations for Defence Excellence |
| IEC | International Electrotechnical Commission |
| IFC | Industry Foundation Classes |
| IGES | Initial Graphics Exchange Specification |
| IMO | International Maritime Organization |
| IRS | Indian Register of Shipping |
| ISO | International Organization for Standardization |
| JSON | JavaScript Object Notation |
| JT | Jupiter Tessellation (Siemens 3D format) |
| JWT | JSON Web Token |
| LAS / E57 / PTS | Point cloud data formats |
| LDAP | Lightweight Directory Access Protocol |
| LR | Lloyd's Register |
| MBSE | Model-Based Systems Engineering |
| MDL | Mazagon Dock Shipbuilders Limited |
| MeitY | Ministry of Electronics and Information Technology |
| MIL-SPEC / MIL-STD | Military Specification / Standard |
| MinIO | S3-compatible object storage server |
| ML | Machine Learning |
| mTLS | Mutual Transport Layer Security |
| NER | Named Entity Recognition |
| NSGA-II | Non-dominated Sorting Genetic Algorithm II |
| NVMe | Non-Volatile Memory Express |
| NX | Siemens NX CAD/CAM/CAE |
| OCC | OpenCascade Technology |
| OCR | Optical Character Recognition |
| OData | Open Data Protocol |
| ONNX | Open Neural Network Exchange |
| PDAL | Point Data Abstraction Library |
| PKI | Public Key Infrastructure |
| PLM | Product Lifecycle Management |
| PRD | Product Requirements Document |
| PS-71 | Problem Statement 71 |
| PSF | Python Software Foundation |
| QA | Quality Assurance |
| RACI | Responsible, Accountable, Consulted, Informed |
| RAG | Retrieval-Augmented Generation |
| RBAC | Role-Based Access Control |
| REST | Representational State Transfer |
| RG | Review Gate |
| ROC-AUC | Receiver Operating Characteristic — Area Under Curve |
| RPO / RTO | Recovery Point Objective / Recovery Time Objective |
| RSAL / SSPL | Redis Source Available License / Server Side Public License |
| SAM 2 | Segment Anything Model 2 |
| SBOM | Software Bill of Materials |
| SHA-256 | Secure Hash Algorithm, 256-bit |
| SHAP | SHapley Additive exPlanations |
| SLA | Service Level Agreement |
| SME | Subject Matter Expert |
| SoW | Scope of Work |
| SRS | Software Requirement Specification |
| SSO | Single Sign-On |
| SSoT | Single Source of Truth |
| STEP | Standard for the Exchange of Product model data (ISO 10303) |
| STQC | Standardisation Testing and Quality Certification |
| TIFF | Tagged Image File Format |
| TLS | Transport Layer Security |
| UAT | User Acceptance Testing |
| UTS | Ultimate Tensile Strength |
| UUID | Universally Unique Identifier |
| Uvicorn | ASGI web server for Python |
| VRAM | Video RAM |
| WBS | Work Breakdown Structure |
| XCAF | Extended Compound Application Framework (OpenCascade) |
| XGBoost | eXtreme Gradient Boosting |
| XML | Extensible Markup Language |
| YOLO | You Only Look Once (object detection) |

---

## 39. Reference & Source Documents

### 39.1 Source document register

| # | Document | Origin | Authority | Notes |
|---|---|---|---|---|
| S1 | `Annexure-I-SoW_iDEX_71.docx` — PRD / Scope of Work, Rev 00, 13 Jul 2026 | MDL | **Highest.** Requirements, scope, NFRs, phases, KPIs, acceptance | Deliberately limited to the "what"; does not prescribe solution |
| S2 | `2_AI_tool_No_71.pdf` — PS-71 problem brief | MDL | High. The three Tasks to Perform | 2 pages |
| S3 | `1_ANNEXURE_II Technical evaluation and compliance questionnaire.pdf` | MDL form, Arcaisys responses | High for disclosure & compliance commitments | 43 pages. Contains the binding §8.2 AI model disclosure, §10 Functional Compliance Matrix and §4 prior project register |
| S4 | `AURORA_Annexure1_PS71.pdf` — Proposed Solution | Arcaisys | Medium. Deliverables D-01→D-15 | 11 pages. **Duration and milestone/cost tables are stale** — see §42 |
| S5 | `AURORA_Annexure2_PTS71.pdf` — Proposed Technical Solution | Arcaisys | Medium. Architecture and engine detail | 27 pages. **Neo4j references are stale** — see §42 |
| S6 | `3_Arcaisys_Concept_Note_PS71_AURORA.pdf` | Arcaisys | Low-medium. Elaboration and narrative | 35 pages. **Neo4j references stale** |
| S7 | `2_Detailed_Project_Timeline.pdf` | Arcaisys | Medium for phase/milestone structure | 6 pages. **This is the surviving 12-month plan** |
| S8 | `6_Return_on_Investment.pdf` | Arcaisys | **None technically.** Commercial narrative | 7 pages |
| S9 | `5_Market_Potential_and_Applicability_Elsewhere.pdf` | Arcaisys | **None technically.** Commercial narrative | 8 pages |
| S10 | `AURORA_Feature_List.md` | Derived (Arcaisys/AI) | Superseded by §22 of this file | Retained as a standalone extract |

**Text coverage:** the full text of S1–S9 is consolidated into this document. **Two categories are not:**

| Not captured | Where it lives | Consequence |
|---|---|---|
| **9 architecture figures** in S5 (Annexure 2) — Unified System Architecture Overview; Digital Twin ER Diagram; Dependency Knowledge Graph; Impact Propagation BFS Flow (cable tray relocation cascade); Engine Stack End-to-End Data Flow; CAD Parsing Pipeline; CAD-BOM Four-Signal Matching Flow; Compliance Engine Evaluation Workflow; System Integration Architecture / API Gateway Topology | S5 only, as page images | §13.4 contains an equivalent ASCII data flow, but the submitted diagrams themselves exist nowhere else. **S5 must be retained.** |
| **Conceptual dashboard mockups** in S6 (Concept Note §1.10) — CAD-BOM Sync, Drawing Synchronization, Compliance Validation views | S6 only, as page images | §23.3 specifies panel contents in text. The visual mockups exist nowhere else. Note these were declared as AI-generated conceptual representations, not production designs |

### 39.2 Evidence & validation sources

| Claim | Evidence | Strength |
|---|---|---|
| ~25% of changes occur post contract-design finalisation | MDL's own stated commercial project data (S1 §2.2, S2) | Customer-asserted — strongest possible basis |
| Prior AI/GenAI delivery capability | Four closely-aligned projects with RAG, knowledge graph, NER, semantic search, rule-based reasoning and explainable AI with source citations — see §39.3 | Moderate. Technique overlap is real and directly relevant; scale and sector are not naval |
| Shipbuilding / classification-society domain experience | **IRCLASS Systems and Solutions Pvt Ltd** — IRS Auditing Software for ships, on-prem, portable install (Mar–Oct 2013). Work experience letter available on request | **The strongest domain card in the bid.** IRCLASS is the Indian Register of Shipping's own entity. Caveats: 2013, developer role rather than delivery ownership, and no AI/GenAI content |
| On-premise deployment experience | IRCLASS project deployed on-prem | Weak but non-zero. Air-gapped specifically: none |
| Solution technical soundness | Reviewed by senior faculty at CDAC-Mumbai | Informal review, not certification |
| Air-gapped deployment capability | Architecture design only | **No deployment evidence.** This is a scored criterion (10 points) and we have no track record |
| Product maturity | Research stage, 0 installations | Disclosed honestly |

### 39.3 Prior project register (as submitted, Annexure-II §4)

**4A — Relevant Domain Experience**

| Client / End-User | Sector | Scope | Duration | AI/GenAI | Deployment | Status | Evidence |
|---|---|---|---|---|---|---|---|
| **IRCLASS Systems and Solutions Pvt Ltd** | Ship auditing software | IRS Auditing Software for ships — portable install (pendrive) onto ship machines | 20 Mar 2013 – 15 Oct 2013 | None. Developer role | **On-Prem** | Completed | Work experience letter on request |
| Internal (Arcaisys) | Software engineering | **Meridian Lite** — AI hallucination reduction and prevention layer | 15 May – ongoing (proposed end December) | Knowledge Graph, LLM, RAG | Cloud | Ongoing | — |

**4B — Similar / Closely-Aligned Experience**

| Client / End-User | Problem solved | Techniques applied | Demonstrable |
|---|---|---|---|
| **Synergy Medtech Solutions** | AI-powered engineering decision-support platform: document interpretation, regulatory compliance verification, dependency analysis, impact assessment, workflow-based approvals over complex interdependent data | LLM, RAG, NLP, NER, document classification, semantic search, knowledge-graph relationship mapping, rule-based reasoning, information extraction, recommendation engines, predictive analytics, explainable AI with source citations, dashboard analytics | Reference call |
| **The GoPT Physiotherapy** | Centralised multi-branch operations platform: workflow execution, resource planning, scheduling, process coordination, approval workflows | Workflow automation, business rule engines, scheduling optimisation, decision-support logic, operational analytics, RBAC workflow management | Reference call |
| **JR Engineering Works** | Digital Workshop Management System: production planning, inventory management, job tracking, material traceability, workflow execution | Workflow automation, business rule engines, production workflow optimisation, inventory tracking, KPI monitoring, dashboards | Reference call |
| **Mr. Ranjeet Rajan (Patent Lawyer)** | AI-powered prior-art intelligence platform: document understanding, dependency mapping, semantic impact analysis, traceable decision support across interconnected technical artefacts. Sources — Google Patents, Espacenet, WIPO PATENTSCOPE, USPTO, InPASS, The Lens | LLM, RAG, NLP, NER, semantic search, vector embeddings, knowledge graph construction, citation analysis, similarity ranking, explainable AI with source traceability | Video |

> **Internal note.** The evidence base is the weakest part of the bid, but it is **stronger than a first read suggests**. Criteria 1, 5 and 7 total 45 of 100 points. The strongest asset is the **IRCLASS engagement** — IRCLASS is the Indian Register of Shipping's own entity, IRS is AURORA's primary rule framework, and the deployment was on-prem. It is also 13 years old, was a developer role rather than a delivery ownership, and contains no AI. The Synergy Medtech project is the closest functional analogue to AURORA (compliance verification + dependency analysis + impact assessment + approval workflow) and is reference-callable. What is genuinely absent is **air-gapped deployment experience** and **any production installation of a comparable product**. The technical response still has to carry the bid, but the domain and technique evidence is real and should be pressed harder than the submission currently does.

---

## 40. Traceability Matrices

### 40.1 Requirement → Design mapping

See §22 Appendices (below) for the full FR and NFR coverage maps against feature IDs.

### 40.2 Requirement → Deliverable mapping

| Requirement group | Deliverable |
|---|---|
| FR-01 → FR-05 | D2 (Data Ingestion & Knowledge Base), D-01, D-08 |
| FR-06 → FR-09 | D3, D-10, D-11 |
| FR-10 → FR-12 | D4, D-02, D-03 |
| FR-13 → FR-15 | D3, D-09, D-01 |
| FR-16 → FR-19 | D4, D-13 |
| FR-20 → FR-23 | D3/D4/D5, D-04, D-14 |
| FR-24 → FR-26 | D5, D-05, D-06 |
| NFR-01, NFR-02 | D7, D-06 |
| NFR-03, NFR-12 | D5, D-06 |
| NFR-04, NFR-07 | D-04, D-10, D-14 |
| NFR-05, NFR-06 | D5, D6 |
| NFR-08 | D-12 |
| NFR-09, NFR-10, NFR-11 | D2, D5, D-05 |

### 40.3 Requirement → Test mapping

> **Not yet defined.** **Trigger:** Phase 1; formalised in D6 Testing Report. Each FR must map to at least one acceptance test and each NFR to at least one verification procedure. Air-gap (NFR-01), RBAC (FR-24) and audit (FR-25) have named verification scenarios already — see §27.4.

### 40.4 Requirement → Code mapping

> **Not yet defined.** **Trigger:** Phase 1 development start. Convention proposed: feature ID (`F-XXX-NN`) referenced in module docstrings and commit messages, enabling automated matrix generation.

---

## 41. Logs

### 41.1 Decision log

| ID | Date | Decision | Rationale | Alternatives considered | Status |
|---|---|---|---|---|---|
| DL-01 | Pre-submission | Deterministic-first architecture; ML excluded from compliance determination paths | Citability and reproducibility are regulatory requirements (NFR-04). A model cannot cite the clause that caused its output | LLM-based rule evaluation; hybrid scoring | Accepted, immutable |
| DL-02 | Post-submission | **ArcadeDB** replaces Neo4j as graph database | Broader feature set; multi-model reduces store count; already the disclosed component in §8.2 | Neo4j Community, JanusGraph, RDF4J | Accepted |
| DL-03 | Post-submission | **Drools** as the deterministic rule engine | Mature; decouples rule authoring from application code as NFR-09/NFR-10 require; already disclosed in §8.2 | Custom evaluator, OpenL Tablets, Easy Rules | Accepted |
| DL-04 | Post-submission | Retain **all four ML libraries**; select empirically per task | No basis to pre-commit before seeing MDL data. Selection is a Phase 2 measurement, not a bid-time guess | Single-library commitment | Accepted |
| DL-05 | Post-submission | **GenAI/RAG layer classified non-core**, low priority, deferrable | Entered scope in the final bid draft; no mandatory requirement depends on it; 12-month compression demands a deferrable buffer | Treat as core; drop entirely | Accepted |
| DL-06 | Post-submission | **12-month** delivery plan | Revised from the original 20-month proposal | 20-month plan | Accepted |
| DL-07 | Pre-submission | Deterministic cold-start mode for CAD–BOM matching | Removes the dependency on historical training data being available, which is outside our control (A-06) | ML-only matching | Accepted |
| DL-08 | Pre-submission | Change-triggered delta compliance mode | A full-system compliance dump on every change is operationally ignored. Change-scoped output is what makes T1 usable | Full re-scan every run | Accepted |
| DL-09 | Pre-submission | Drawing modification limited to DXF write and PDF overlay | Writing into parametric CAD drawing files from outside the CAD system is fragile | Direct parametric CAD manipulation | **Provisional** — pending MDL direction (OQ-02) |
| DL-10 | Pre-submission | No geometry write-back into CAD models | Risks corrupting the design authority's model; re-export via webhook is safer | Direct CAD geometry write-back | **Provisional** — pending MDL confirmation on T2 (OQ-03) |
| DL-11 | 2026-08-08 | As-installed / point cloud scope moved from "out" to **conditional** | MDL direction pending; premature to close it out | Keep as permanently out of scope | Accepted |
| DL-12 | 2026-08-08 | Cost and budget **excluded** from the SSoT | The milestone schedule was built on the dead 20-month plan; carrying stale figures is worse than carrying none | Retain as-submitted with a caveat; publish a draft re-phasing | Accepted |

### 41.2 Change log

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-08-08 | Initial SSoT created from the nine source documents plus the post-submission decisions in §41.1 | — |

### 41.3 Revision history

| Version | Date | Summary |
|---|---|---|
| 1.0 | 2026-08-08 | Bid baseline. Consolidates S1–S9, incorporates DL-01→DL-12, excludes cost, records superseded positions in §42 |

### 41.4 Approval history

> **Not yet defined.** No approval workflow established for this document. **Trigger:** §32.1 role assignment.

---

## 42. Superseded Information

**Do not use anything in this section.** It is recorded solely because these statements are still present in documents MDL holds, and anyone reading those documents needs to know they are stale.

| # | Superseded statement | Where it still appears | Current truth | Correction needed |
|---|---|---|---|---|
| SI-01 | Project duration is **20 months** with a Phase 6 running months 15–20 | S4 §4 (timeline table), S4 §5 (milestone table), S5 cover page ("Duration 20 Months") | **12 months**, D1–D7 / M1–M7 | Yes — correct before SRS baseline |
| SI-02 | Graph database is **Neo4j**; impact propagation over Neo4j; Neo4j in the glossary | S4 §2 (Key Technologies), S5 §5.1 L3, §5.2, glossary; S6 §4.2 | **ArcadeDB** | Yes — and note this contradicts the §8.2 disclosure MDL used for security clearance |
| SI-03 | Rule engine unnamed / implied custom | S5 §5.4.3 | **Drools** | Yes — add explicitly |
| SI-04 | CAD–BOM confidence scoring is **XGBoost** specifically | S4 §2, S4 D-09, S5 §5.4.2 | Candidates benchmarked across XGBoost, LightGBM, Scikit-learn, PyTorch; best selected empirically | Soften wording to "gradient-boosting / ML confidence scoring" |
| SI-05 | Milestone payment schedule M-01→M-07 totalling **₹1,80,00,000**, phased across 20 months | S4 §5 | **Void.** Built on the dead 20-month plan | Yes — re-phase before contract negotiation (AI-02) |
| SI-06 | Point cloud, photogrammetry and as-installed registration are **out of scope** (unqualified "NO") | S3 §10 FCM rows 3–5; S3 §6.4 | **Conditional** — not finalised, may or may not be in scope | Flag as conditional in any restatement |
| SI-07 | Drawing support includes **DWG** | S6 §1.8 | Working assumption is DXF read/write and PDF overlay. DWG **write** is not scoped. Awaiting MDL direction | Do not restate DWG write capability until confirmed |
| SI-08 | GenAI layer positioned as a core capability | S3 §7 (AI/GenAI Technical Capability responses) | **Non-core, low priority, deferrable.** Not reflected in the L1–L7 architecture in S5 | Add a note to S5 §5 positioning the layer above L7 as optional |
| SI-09 | Phase 6 "Production Enhancements", months 15–20 | S4 §4 | **Void.** Content must be absorbed into M6/M7 or formally dropped | Yes — part of the 20→12 re-plan (AI-01) |

---

## 43. Open Questions, Pending Decisions & Actions

### 43.1 Open questions — with MDL

| ID | Question | Blocks | Raised |
|---|---|---|---|
| OQ-01 | Is as-installed / point cloud registration in scope? (§6.4) | Phase 1 scope freeze; CV/3D component retention; R-10 | Pending |
| OQ-02 | What drawing formats and write paths are required? Specifically: is DWG write required, and to which version? Is PDF annotation overlay acceptable for released drawings? Is the CATIA/NX re-export path workable within MDL's CAD licensing? | D-13 design; DL-09 | Pending |
| OQ-03 | **Does Task 2 require geometry write-back into the 3D model, or does detect-and-trigger satisfy it?** | Architecture; R-11; DL-10 | Pending |
| OQ-04 | Which CAD platforms and versions are used across MDL projects? | Phase 0 format assessment; R-04 | Submitted in bid |
| OQ-05 | What BOM maturity and standardisation exists across programmes? | Registry schema alignment | Submitted in bid |
| OQ-06 | Which classification societies and defence standards apply to the target projects? | Rule catalog scope; R-02 | Submitted in bid |
| OQ-07 | What configuration management and engineering change processes are currently followed? | Workflow design | Submitted in bid |
| OQ-08 | What integration level is expected with PLM, ERP, CAD and document management? | Connector scope; R-05 | Submitted in bid |
| OQ-09 | Is the "apply the more conservative value" multi-society conflict policy acceptable? | Compliance engine default; R-13 | Not yet raised |
| OQ-10 | What are the licensing terms for the class rule books, specifically regarding ingestion into a searchable knowledge base? | R-14 | Not yet raised |
| OQ-11 | Is "full-ship scale" in Phase 3 acceptance achievable on the budgeted ~10,000-node tier, or is enterprise hardware expected? | Phase 3 acceptance definition; C-08 | Not yet raised |

### 43.2 Pending decisions — internal

| ID | Decision | Owner | Trigger |
|---|---|---|---|
| PD-01 | Retain or remove YOLOv11 (AGPL-v3), SAM 2, Open3D, PDAL, VTK from the stack and disclosure | Security/compliance lead | Resolution of OQ-01 |
| PD-02 | Redis vs Valkey — resolve the RSALv2/SSPLv1 licence exposure | Architecture lead | Before Phase 1 |
| PD-03 | Team structure and staffing plan (§32.1) | Delivery lead | Contract award |
| PD-04 | Git branching, repository structure, coding standards (§26) | Architecture lead | Phase 1 start |
| PD-05 | Rollback strategy for air-gapped deployment (§28.5) | DevOps lead | Phase 2 |
| PD-06 | Availability/DR targets (§25.3, §25.5) | Delivery lead + MDL IT | Phase 0 |

### 43.3 Action items

| ID | Action | Priority | Owner | Status |
|---|---|---|---|---|
| **AI-01** | **Do the actual 20→12 month re-plan at task level.** Only the headline duration changed; the work breakdown has not been compressed. Phase 6 content (SI-09) must be absorbed or dropped, and the 12 MVP-committed FCM rows re-tested against a 6-month Phase 1 | **Critical** | Delivery lead | Not started |
| **AI-02** | Re-phase the milestone payment schedule against the 12-month plan | **Critical** | Delivery lead | Not started |
| AI-03 | Correct SI-01 → SI-04 and SI-08 in the source documents before SRS baseline | High | Delivery lead | Not started |
| AI-04 | Raise OQ-03 (Task 2 write-back) with MDL — this is an architectural question, not a detail | **Critical** | Delivery lead | Not started |
| AI-05 | Raise OQ-01 (as-installed scope) with MDL | High | Delivery lead | Not started |
| AI-06 | Raise OQ-09, OQ-10, OQ-11 with MDL | Medium | Delivery lead | Not started |
| AI-07 | Resolve PD-01 and PD-02 (licence exposures) | Medium | Security/compliance lead | Not started |
| AI-08 | Assign document owner and approvers for this SSoT (§0.1, §41.4) | Medium | — | Not started |

---

## 44. Lessons Learned & Postmortems

> **Not yet applicable.** No phase has completed. **Trigger:** first review gate (RG-1).

Observations already worth carrying forward into the next bid, regardless of outcome:

| # | Observation |
|---|---|
| LL-01 | The bid pack accumulated four separate technology-stack statements across five documents, and they contradicted each other on the graph database, rule engine and ML library. A single technology decision register maintained from day one — this file's §14.1 — would have prevented that. The contradiction landed in a document used for **security clearance**, which is the worst possible place for it |
| LL-02 | The GenAI layer was added in the final draft and never propagated into the architecture document, leaving the questionnaire promising capability the architecture did not contain. Late additions need an architecture-impact check, not just a section insert |
| LL-03 | A duration change from 20 to 12 months was applied to the headline but not to the underlying plan, milestones or payment schedule. Changing a number is not the same as changing a plan (AI-01, AI-02) |
| LL-04 | Components were disclosed in the mandatory AI Model Disclosure that no committed feature uses (YOLOv11, SAM 2, Open3D, PDAL, VTK). Disclosure should follow scope, not aspiration — an unused AGPL-v3 dependency in a defence procurement is pure downside |
| LL-05 | The bid's strongest domain evidence — the IRCLASS / IRS ship auditing engagement — is buried in a table in §4A and never referenced in any narrative section of any other document. Evidence that is not surfaced does not score |
| LL-06 | PT-04 ("zero critical false negatives") was committed as an absolute. It is defensible only with the qualifier "within validated rule scope". Absolute claims in a bid become absolute obligations in a contract |

---

*End of document.*
