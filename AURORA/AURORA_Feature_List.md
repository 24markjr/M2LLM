# AURORA — Complete Feature List

**Automated Unified Reasoning and Optimization Architecture**
AI Tool for Design Optimization (Class Rules, Standards & Regulations Compliance) & 3D–BOM Synchronization

| Field | Detail |
|---|---|
| Programme | MDL iDEX DRISHTI Innovation Challenge — Problem Statement 71 (Sl. No. 71) |
| Customer | Mazagon Dock Shipbuilders Limited (MDL), Ministry of Defence, GoI |
| Vendor | Arcaisys |
| Deployment | Fully on-premise / air-gapped, no internet dependency |
| Duration | **12 months** (revised down from the original 20-month plan) |
| Document purpose | Consolidated list of every feature that must exist at final project completion |
| Source documents | SoW/PRD (Annexure-I), MDL PS-71 brief, Annexure-II Technical Questionnaire, AURORA Annexure 1 & 2, Concept Note, Project Timeline, ROI, Market Potential |

---

## How to read this document

- **ID** — stable feature identifier, `F-<MODULE>-<NN>`.
- **Priority** — `M` = mandatory per SoW, `D` = desirable per SoW, `P` = proposal commitment (Arcaisys committed it even though SoW does not mandate it), `L` = low priority / non-core (build only after all M/D/P items are complete), `C` = conditional (in or out depending on a pending MDL decision).
- **Trace** — traceability to SoW functional requirements (`FR-xx`), non-functional requirements (`NFR-xx`), Functional Compliance Matrix rows (`FCM-n`), and Arcaisys deliverables (`D-xx`).
- **Phase** — earliest phase in which the feature must be working.

| Phase | Name | Months | Milestone / Deliverable |
|---|---|---|---|
| `P0` | Capability Demonstration | Pre-start | Demo report, video, feasibility assessment |
| `P1` | Pilot / MVP | M0–M6 | M1–M3, D1–D3 |
| `P2` | Full Development | M6–M10 | M4–M5, D4–D5 |
| `P3` | Secure Deployment & Scale | M10–M12 | M6–M7, D6–D7 |

The three MDL "Tasks to Perform" that everything below must ultimately satisfy:

1. Highlight changes in design drawings w.r.t. classification rules, integration requirements and regulatory requirements.
2. Incorporate detail-design changes into the 3D model.
3. Reflect approved-drawing changes into production drawings.

---

## Baselined technology decisions

These supersede any conflicting statement in the earlier proposal documents. Where an annexure or the concept note says otherwise, this table wins.

| Area | Decision | Supersedes |
|---|---|---|
| Project duration | **12 months** | The 20-month plan in Annexure 1 & 2 (Phase 6 to month 20) is withdrawn. Milestones follow the Detailed Project Timeline (M1–M7, D1–D7). |
| Graph database | **ArcadeDB** | Neo4j, named in Annexure 1, Annexure 2 and the Concept Note. ArcadeDB selected for its broader feature set. Matches the §8.2 AI Model Disclosure. |
| Deterministic rule engine | **Drools** | The unnamed custom rule evaluator described in Annexure 2 §5.4.3. Matches the §8.2 disclosure. |
| ML libraries | **XGBoost / LightGBM, Scikit-learn, PyTorch** — all four carried; the model that performs best on validation data is selected per task | The single-library commitments in Annexure 1/2 and the questionnaire stack table. Selection is an empirical decision made during Phase 2. |
| GenAI / RAG layer | **Non-core, low priority.** Added in the final proposal draft; deliver only after all mandatory and desirable capability is complete. | Any reading of the questionnaire that treats the LLM layer as core scope. |
| As-installed registration (point cloud / photogrammetry) | **Not finalised.** May or may not be in scope. | The unqualified "NO" in FCM rows 3–5. Treated as conditional pending MDL direction. |
| Drawing format support | **To be set by MDL direction.** DXF read/write and PDF annotation are the working assumption; DWG write and parametric-CAD handling await confirmation. | The differing format claims in the Concept Note (DXF/DWG/PDF), Annexure 2 §5.7 and FCM row 1. |

---

## 1. Data Ingestion & Normalisation (`ING`)

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

## 2. Unified Component Registry / Digital Twin Core (`DTC`)

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

## 3. Rule Knowledge Base & Rule Digitisation (`RKB`)

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

## 4. Dependency Knowledge Graph (`KG`)

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

## 5. CAD–BOM Synchronisation Engine (`SYN`)

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

## 6. Compliance Validation Engine (`CMP`)

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

## 7. Change Impact Prediction & Propagation (`IMP`)

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

## 8. Design Optimisation Engine (`OPT`)

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

## 9. Drawing Synchronisation & Revision Engine (`DRW`)

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

## 10. Configuration, Version & Baseline Management (`CFG`)

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

## 11. Classification Society Submission Workflow (`CLS`)

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

## 12. Review, Approval & Human-in-the-Loop Workflow (`WKF`)

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

## 13. GenAI, RAG & Engineering Assistant (`GAI`) — non-core

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

**Dependency note:** deferring this module has no effect on any mandatory requirement. FR-20 (explainability with source citations) is satisfied by §14 through deterministic clause citation, not by the LLM. FR-21 and FR-23 (reports and export) are satisfied by §15 through templated generation. Nothing in §1–§12 or §14–§23 depends on this layer.

---

## 14. Explainability, Confidence & Traceability (`XAI`)

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

## 15. Reporting & Export (`RPT`)

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

## 16. Decision Intelligence Dashboard (`DSH`)

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

## 17. Integration & API Layer (`INT`)

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

## 18. Security, Access Control & Audit (`SEC`)

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

## 19. Deployment, Air-Gap & Operations (`OPS`)

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

## 20. Model Lifecycle & MLOps (`MLO`)

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

## 21. Administration & Configuration (`ADM`)

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

## 22. Performance & Quality Targets (`PRF`)

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

## 23. Testing, Validation & Documentation Deliverables (`DOC`)

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

## 24. Conditional Scope — pending MDL decision (`CND`)

Not committed. These features are in or out depending on directions still to come from MDL. They are listed with IDs so that if MDL confirms them, they slot into the plan without renumbering, and so that effort and schedule impact can be quoted against a defined item rather than estimated from scratch.

### 24.1 As-installed / as-built registration — **not finalised**

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

### 24.2 Drawing format coverage — **awaiting MDL direction**

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

## 25. Explicitly Out of Scope

Recorded so scope creep can be detected and so future add-on discussions start from an agreed baseline.

| Item | Status | Source |
|---|---|---|
| Issuing formal class certification or approval decisions | Out — retained by classification society and design authority | SoW §5.2 |
| Procurement of PLM / ERP / CAD licences or physical infrastructure | Out | SoW §5.2 |
| Running FEA/CFD solvers as such — system flags where re-analysis is required | Out (solver execution optional, not mandated) | SoW §5.2 |
| Automated submission to classification-society portals | Out — package preparation only | SoW §5.2 |
| Autonomous approval of any engineering decision | Permanently out — human authority is mandatory | HITL layer |

Point cloud ingestion, photogrammetry and as-installed registration are **no longer listed here** — they have moved to §24.1 as conditional scope pending MDL decision.

**Designed-for extensibility (future paid enhancements):** simulation-assisted optimisation with PyTorch surrogate models; multi-vessel-programme scale-out; enterprise HA cluster deployment at full-ship scale.

---

## 26. Decision Record & Remaining Open Items

### 26.1 Resolved — decisions taken

The following conflicts across the proposal document set have been closed. The decision is authoritative; the superseded position should be corrected in the source documents before the SRS is baselined, so that the submitted pack and the build plan agree.

| # | Conflict | Resolution | Documents needing correction |
|---|---|---|---|
| 1 | Project duration: 12 months (Timeline) vs 20 months (Annexure 1 & 2) | **12 months.** The 20-month plan was the initial proposal and has been revised down. Milestones follow D1–D7 / M1–M7. | Annexure 1 §4 timeline table and §5 milestone table; Annexure 2 cover page ("Duration 20 Months"); the ₹1.80 Cr milestone schedule is built on 20 months and must be re-phased to 12. |
| 2 | Graph database: Neo4j vs ArcadeDB | **ArcadeDB**, selected for its broader feature set. Already matches the §8.2 security-clearance disclosure. | Annexure 1 §2 (Key Technologies), Annexure 2 §5.1 L3 / §5.2 / glossary, Concept Note §4.2. All say Neo4j. |
| 3 | Rule engine: unnamed custom evaluator vs Drools | **Drools.** Already matches the §8.2 disclosure. | Annexure 2 §5.4.3 describes the evaluation workflow without naming the engine — add Drools explicitly. |
| 4 | ML library: XGBoost/LightGBM vs Scikit-learn/PyTorch | **All four retained.** Candidates are benchmarked per task during Phase 2 and the best performer on validation data is selected. | No correction strictly required, but Annexure 1/2 should be softened from "XGBoost" to "gradient-boosting / ML confidence scoring" so the disclosure and the annexures do not appear to contradict. |
| 5 | GenAI layer present in questionnaire, absent from architecture | **Non-core, low priority** (§13). Added in the final draft; deliver last, defer first if schedule tightens. No mandatory requirement depends on it. | Optional: add a one-line note to Annexure 2 §5 acknowledging the layer sits above L7 as an optional enhancement, so the questionnaire and architecture do not read as disconnected. |

### 26.2 Open — awaiting MDL direction

| # | Item | Status | What is needed |
|---|---|---|---|
| 6 | As-installed / point cloud registration | **Not finalised** — may or may not be in project scope. Captured as conditional features F-CND-01 to F-CND-06 (§24.1). | An MDL decision. If confirmed, scope, cost and schedule impact must be agreed separately — this is a material addition to a 12-month plan. If declined, review the CV/3D components in the §8.2 disclosure for removal. |
| 7 | Drawing format coverage | **Awaiting MDL direction** on formats and toolchain. Working assumption documented in §24.2. | Confirmation on DWG write support and version, acceptability of PDF annotation overlay for released drawings, and workability of the CATIA/NX re-export path within MDL's CAD licensing. |

### 26.3 Closed without action

Items 8–11 of the previous revision (product maturity vs MVP commitments, MDL Task 2 write-back interpretation, unanswered questionnaire sections, hardware budget boundary) are noted as reviewed and require no change to this feature list.

---

## Appendix A — SoW Functional Requirement Coverage Map

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

## Appendix B — SoW Non-Functional Requirement Coverage Map

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
