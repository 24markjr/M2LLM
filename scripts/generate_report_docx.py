"""Full script to build the complete, publication-grade JARVIS Engineering Report (.docx)."""

import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def build_report():
    doc = Document()
    
    # Page setup - Standard 1 inch margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    def set_cell_background(cell, fill_hex):
        tcPr = cell._element.get_or_add_tcPr()
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
        tcPr.append(shd)

    def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
        tcPr = cell._element.get_or_add_tcPr()
        tcMar = parse_xml(
            f'<w:tcMar {nsdecls("w")}>'
            f'  <w:top w:w="{top}" w:type="dxa"/>'
            f'  <w:bottom w:w="{bottom}" w:type="dxa"/>'
            f'  <w:left w:w="{left}" w:type="dxa"/>'
            f'  <w:right w:w="{right}" w:type="dxa"/>'
            f'</w:tcMar>'
        )
        tcPr.append(tcMar)

    def set_table_borders(table, color="D1D5DB", sz="4", val="single"):
        tblPr = table._element.xpath('w:tblPr')
        if tblPr:
            borders = parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                f'  <w:insideV w:val="none"/>'
                f'  <w:left w:val="none"/>'
                f'  <w:right w:val="none"/>'
                f'</w:tblBorders>'
            )
            tblPr[0].append(borders)

    def add_callout(text, title=None, border_color="2563EB", bg_color="F0F7FF"):
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        tbl.columns[0].width = Inches(6.5)
        
        cell = tbl.cell(0, 0)
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
        
        tcPr = cell._element.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>'
            f'  <w:top w:val="none"/>'
            f'  <w:bottom w:val="none"/>'
            f'  <w:right w:val="none"/>'
            f'</w:tcBorders>'
        )
        tcPr.append(borders)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        if title:
            run_title = p.add_run(f"{title}\n")
            run_title.bold = True
            run_title.font.name = "Calibri"
            run_title.font.size = Pt(10.5)
            run_title.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
            
        run_text = p.add_run(text)
        run_text.font.name = "Calibri"
        run_text.font.size = Pt(10)
        run_text.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def format_row(row, bg_hex, text_color_rgb, bold=False, font_size=9):
        for cell in row.cells:
            set_cell_background(cell, bg_hex)
            set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.15
                for r in p.runs:
                    r.bold = bold
                    r.font.name = "Calibri"
                    r.font.size = Pt(font_size)
                    r.font.color.rgb = text_color_rgb

    def h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(20)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(16)
        r.bold = True
        r.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
        return p

    def h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(12.5)
        r.bold = True
        r.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        return p

    def h3(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(11)
        r.bold = True
        r.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
        return p

    def body_p(text, bold_prefix=None):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.bold = True
            r_pre.font.name = "Calibri"
            r_pre.font.size = Pt(10)
            r_pre.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        return p

    def bullet_p(text, bold_prefix=None):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.bold = True
            r_pre.font.name = "Calibri"
            r_pre.font.size = Pt(9.5)
            r_pre.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        return p

    def styled_table(headers, data, col_widths=None):
        tbl = doc.add_table(rows=len(data) + 1, cols=len(headers))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        set_table_borders(tbl)
        
        hdr_row = tbl.rows[0]
        for i, title in enumerate(headers):
            hdr_row.cells[i].text = title
        format_row(hdr_row, "1E3A8A", RGBColor(0xFF, 0xFF, 0xFF), bold=True, font_size=9)
        
        for r_idx, row_data in enumerate(data):
            row = tbl.rows[r_idx + 1]
            bg_color = "F9FAFB" if r_idx % 2 == 1 else "FFFFFF"
            for c_idx, val in enumerate(row_data):
                row.cells[c_idx].text = str(val)
            format_row(row, bg_color, RGBColor(0x37, 0x41, 0x51), bold=False, font_size=8.5)
            
        if col_widths:
            for row in tbl.rows:
                for idx, w in enumerate(col_widths):
                    row.cells[idx].width = Inches(w)
                    
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        return tbl

    # --- TITLE / HEADER ---
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(24)
    title_p.paragraph_format.space_after = Pt(4)
    r_title = title_p.add_run("JARVIS: Adaptive, Evidence-Driven AI Orchestration & Investigation Engine")
    r_title.bold = True
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(22)
    r_title.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(16)
    r_sub = sub_p.add_run("Comprehensive Software Engineering & System Architecture Report\nIncorporating Requirements, Implementation Architecture, Verification, Quality Benchmarks, and GUI Specifications")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = RGBColor(0x4B, 0x55, 0x63)

    add_callout(
        "\"Most systems built on a language model ask it how confident it is. This one never does. "
        "Every claim is bound to the evidence that produced it. A finding cites source locators (e.g. aurora_report.txt:r12), "
        "and those citations are resolved against locators the tasks actually returned. Confidence is strictly computed "
        "from what resolved—never asserted. An empty result is a valid answer; verification is independent; "
        "and the execution plan is dynamically replanned when evidence gaps emerge.\"",
        title="Core Engineering Axiom",
        border_color="1E3A8A",
        bg_color="EFF6FF"
    )

    # ==========================================
    # 1. SYSTEM REQUIREMENTS
    # ==========================================
    h1("1. System Requirements")
    body_p("The JARVIS orchestration engine is designed as an autonomous, evidence-driven investigation platform capable of converting natural language objectives into verifiable, dependency-aware task graphs. Below are the functional, non-functional, hardware, software, and machine learning model specifications.")

    h2("1.1 Functional Requirements (FR)")
    req_data = [
        ["FR-01", "Objective Decomposition", "Engine must parse natural language objectives into structured intents, classifying goals, identifying target entities, operations, and extraction bounds."],
        ["FR-02", "Task Graph Generation", "Generate a Directed Acyclic Graph (DAG) of executable tasks with strict dependency awareness and topological wave scheduling."],
        ["FR-03", "Dynamic Tool Routing", "Route operations to registered tools (text loaders, table parsers, OCR, vision, STT, web, DB) using deterministic matching with LLM tie-breaking."],
        ["FR-04", "Evidence Binding & Locator Resolution", "Bind candidate claims to exact character/line/page locators (doc:rN, doc:pN). Unresolvable citations must be tagged UNRESOLVED, never silently dropped."],
        ["FR-05", "Relevance Gating & Confabulation Suppression", "Filter candidate findings against the user's objective prior to synthesis to ensure consistent negative cases yield zero findings."],
        ["FR-06", "Evidence Gap Detection", "Deterministically identify missing corroborating evidence or unresolved references and trigger dynamic in-flight replanning."],
        ["FR-07", "Independent Verification", "Verify findings using independent lexical (TF-IDF/shared identifier) and composite model verifiers isolated from the generation pipeline."],
        ["FR-08", "Multimodal Document Ingestion", "Ingest and parse diverse formats: plain text, Markdown, CSV, Excel (.xlsx), Word (.docx), PDF (vector & scanned via OCR), audio, video, and logs."],
        ["FR-09", "Knowledge Graph Extraction", "Extract entities, relationships, temporal statements, and cross-document contradictions into an interactive property graph."],
        ["FR-10", "Cryptographic Chain of Custody", "Maintain an immutable, append-only custody log tracking SHA-256 hashes, acquisition times, parsers, and citations for all evidence items."],
        ["FR-11", "Cross-Mission Episodic Memory", "Persist entities, findings, and episodic run summaries in PostgreSQL with pgvector embeddings for similarity retrieval."],
        ["FR-12", "Real-Time Event Streaming", "Stream granular operational events (plan diffs, task dispatches, tool results, verification verdicts) over Server-Sent Events (SSE)."]
    ]
    styled_table(["ID", "Requirement", "Specification Description"], req_data, [0.8, 1.8, 3.9])

    h2("1.2 Non-Functional Requirements (NFR)")
    nfr_data = [
        ["NFR-01", "Determinism & Reproducibility", "Runs with pinned seeds and temperature=0.0 must yield identical task topologies, tool selections, and finding classifications."],
        ["NFR-02", "Hard Loop Bounds", "Adaptive replanning, tool calls, and task retries must enforce hard ceiling bounds configured in .env (Invariant #7)."],
        ["NFR-03", "Offline & Air-Gapped Operation", "The core engine, local LLM provider, vector database, and graph store must execute without outbound internet connectivity."],
        ["NFR-04", "Operational Transparency", "No hidden chain-of-thought or raw model deliberation tokens may be persisted or streamed; only operational decisions are logged."],
        ["NFR-05", "LLM Architectural Isolation", "Model invocations are restricted exclusively to app/llm/provider.py. Arbitrary API calls elsewhere fail build linting."],
        ["NFR-06", "Performance Latency", "Local investigations on a standard 4-billion parameter model must complete full execution, reasoning, and report synthesis within 45–90 seconds."],
        ["NFR-07", "Audit Immutability", "Custody events and case logs are append-only. Database triggers must prevent UPDATE and DELETE operations on forensic records."]
    ]
    styled_table(["ID", "Category", "Specification Description"], nfr_data, [0.8, 1.8, 3.9])

    h2("1.3 Hardware and Infrastructure Specifications")
    body_p("The system is optimized for edge deployment on standard workstation/laptop hardware without requiring enterprise cloud GPU clusters:")
    bullet_p("Processor: 8-core modern x86_64 or ARM64 CPU (Intel i7/i9 12th+ Gen, AMD Ryzen 7+, Apple M-series).", "Host CPU: ")
    bullet_p("16 GB minimum, 32 GB recommended to support concurrent model weights, OS cache, and database buffers.", "RAM Memory: ")
    bullet_p("Optional dedicated NVIDIA GPU (6 GB+ VRAM, CUDA 12+) for accelerated Ollama inference, or CPU-native AVX2 inference.", "Acceleration: ")
    bullet_p("15 GB available SSD storage for model weights, vector databases, Neo4j graphs, and local document caches.", "Disk Storage: ")

    h2("1.4 Software & Dependency Specifications")
    bullet_p("Python 3.12.10 (Backend runtime, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PyTorch/RapidOCR/Whisper).", "Python Runtime: ")
    bullet_p("Node.js 20.x or 24.x LTS with npm 11.x (Frontend UI runtime, Vite, React 19, TypeScript 5.7).", "Node.js Environment: ")
    bullet_p("Ollama v0.40+ running locally serving GGUF quantized models over HTTP localhost:11434.", "Inference Server: ")
    bullet_p("Docker 29+ / Docker Compose for containerized infrastructure: PostgreSQL 16 (pgvector) and Neo4j 5 Community.", "Container Engine: ")

    h2("1.5 Model Specifications")
    model_data = [
        ["qwen3:4b", "Ollama", "Reasoning / Primary", "Structured planning, intent analysis, candidate finding generation, and synthesis."],
        ["nomic-embed-text", "Ollama", "Embedding / 768-dim", "Dense semantic representations for workspace documents and memory retrieval."],
        ["qwen2.5vl:3b", "Ollama", "Vision-Language", "Visual scene understanding, diagram interpretation, and keyframe inspection."],
        ["faster-whisper (base)", "CTranslate2", "Speech-to-Text", "Local offline audio transcription for recorded interviews and video audio."]
    ]
    styled_table(["Model Name", "Engine / Format", "Role", "Operational Function"], model_data, [1.3, 1.1, 1.4, 2.7])

    # ==========================================
    # 2. SYSTEM IMPLEMENTATION
    # ==========================================
    h1("2. System Implementation")
    body_p("JARVIS is architected as a Modular Monolith (ADR-001) held together by typed Pydantic contracts and an immutable event stream. It strictly eschews opaque multi-agent chat loops in favor of a compiled, inspectable execution pipeline.")

    h2("2.1 Ten Architectural Invariants")
    body_p("Every component in the codebase adheres to ten non-negotiable architectural invariants enforced via static AST analysis and automated test gates:")
    bullet_p("The LLM is a component, not the architecture. No module calls the model directly except through app/llm/provider.py.", "Invariant 1: ")
    bullet_p("Typed boundaries. Anything crossing component boundaries is a Pydantic model from app/schemas/. No raw dicts.", "Invariant 2: ")
    bullet_p("No hidden chain-of-thought. Emitted events expose operational decisions, never raw model deliberation tokens.", "Invariant 3: ")
    bullet_p("Every run is traceable. Every state transition writes an ExecutionEvent. Runs are 100% reconstructable from event logs.", "Invariant 4: ")
    bullet_p("No fabricated behavior. No mock progress logs or simulated agent outputs presented as real; no hard-coded evaluation metrics.", "Invariant 5: ")
    bullet_p("Modular encapsulation. Each intelligence component is a package with __init__.py, an engine module, and a test module.", "Invariant 6: ")
    bullet_p("Bounded loops. Every adaptive loop has a hard ceiling (MAX_REPLAN_ITERATIONS, MAX_TASK_RETRIES, MAX_TOOL_CALLS).", "Invariant 7: ")
    bullet_p("Determinism where possible. Model temperature (0.0), seeds (42), and tool ordering are pinned and reproducible.", "Invariant 8: ")
    bullet_p("Docs move with code. Phases are not complete until changelogs, bug logs, and ADRs are updated.", "Invariant 9: ")
    bullet_p("External members are interfaces. M2Context, Knowledge, and Verification are consumed via protocols with local fallbacks.", "Invariant 10: ")

    h2("2.2 Pipeline Subsystems & Execution Lifecycle")
    body_p("The execution flow proceeds through nine vertical stages:")
    
    add_callout(
        "OBJECTIVE -> Intent Analysis -> Task Planning -> Task Graph Compilation\n"
        "  -> Wave Execution -> Tool Dispatch -> Evidence Gathering\n"
        "  -> Reasoning Engine -> Relevance Gate -> Finding Extraction\n"
        "  -> Evidence Gap Detection -> [Trigger Replan Loop if Gaps Exist]\n"
        "  -> Independent Verification -> Synthesis -> Final Forensic Report",
        title="Execution Engine State Machine",
        border_color="2563EB",
        bg_color="F8FAFC"
    )

    bullet_p("Analyzes input natural language, identifies target entities, required document inputs, and maps required operations (READ, PARSE, EXTRACT, COMPARE, VERIFY).", "Intent Analyzer (app/orchestration/intent.py): ")
    bullet_p("Translates intent into discrete tasks, establishing strict dependency edges. The PlanTree structure validates acyclicity and groups tasks into parallel waves.", "Execution Planner (app/orchestration/planner.py): ")
    bullet_p("Matches task operations to concrete tools. Routes deterministic operations directly and uses prompt-based classification only when multiple candidate tools qualify.", "Tool Router (app/orchestration/router.py): ")
    bullet_p("Dispatches independent tasks asynchronously within each wave, respecting MAX_PARALLEL_TASKS bounds. Gathers observations into an append-only ContextStore.", "Execution Engine (app/orchestration/execution.py): ")
    bullet_p("Evaluates collected observations against the hypothesis. Candidate findings must cite specific locators. The Relevance Gate discards non-responsive claims (BUG-005).", "Reasoning Engine (app/orchestration/reasoning.py): ")
    bullet_p("Compares candidate claims against cited source text. Missing references generate gap tokens that trigger ReplanningController to insert new tasks in-flight.", "Evidence Gap Detector (app/orchestration/evidence_gap.py): ")
    bullet_p("An isolated verifier (Composite: TF-IDF lexical + secondary model) verifies claim agreement without access to the reasoning chain.", "Verification Engine (app/verification/): ")
    bullet_p("Aggregates verified findings, unresolved citations, integrity hashes, and audit metadata into a finalized Markdown and JSON report.", "Report Synthesizer (app/orchestration/synthesis.py): ")

    h2("2.3 Storage and Persistence Architecture")
    bullet_p("Stores runs, execution tasks, findings, evidence custody events, and vector embeddings using pgvector. Implements append-only database triggers for forensic custody.", "PostgreSQL 16 + pgvector: ")
    bullet_p("Stores the unified knowledge graph—nodes (Entities, Documents, Claims) and edges (MENTIONS, CONTRADICTS, CORROBORATES). Includes in-memory fallback.", "Neo4j 5 Community: ")
    bullet_p("Centralized store assigning SHA-256 hashes, recording acquisition metadata, and providing verifiable custody chains for legal/forensic defensibility.", "Evidence Locker: ")

    # ==========================================
    # 3. TESTING METHODOLOGY
    # ==========================================
    h1("3. Testing Methodology")
    body_p("Testing an autonomous orchestration agent requires a fundamentally different philosophy than standard web services. An agent cannot be tested only by checking that it produces non-empty output. The most dangerous failure modes in AI systems are 'quiet failures'—an agent that reports claims it cannot substantiate, hallucinates contradictions in consistent corpora, or silently misses injected prompt attacks.")

    h2("3.1 Multi-Layered Test Pyramid")
    test_layer_data = [
        ["Unit Tests (59 modules)", "Validates individual components (parsers, schemas, routing, locators) in complete isolation.", "EchoProvider (deterministic fixtures, raises NoFixtureError on unexpected calls)."],
        ["Invariant Tests", "AST-based static checks asserting architectural rules (no LLMs outside provider, no eval, bounded while loops).", "Python ast module source parsing; no model."],
        ["Adversarial Tests", "Hostile payloads, prompt injections, circular task plans, and oversized outputs.", "Simulated attacks, poisoned documents, malformed schemas."],
        ["Integration Tests (10 modules)", "Full lifecycle testing with real PostgreSQL database persistence and schema migrations.", "PostgreSQL test database with transaction rollback."],
        ["Evaluation Suite (14 scenarios)", "End-to-end benchmark measuring factual accuracy, citation precision, and hallucination rate.", "Real local Ollama model (qwen3:4b, temperature=0.0)."],
        ["Frontend Tests", "Component rendering, graph model transforms, citation link resolution, and state reconstruction.", "Vitest, React Testing Library, and TypeScript compiler (tsc)."]
    ]
    styled_table(["Testing Tier", "Scope and Objective", "Execution Environment"], test_layer_data, [1.5, 3.2, 1.8])

    h2("3.2 Test Execution Strategy & Seed Randomization")
    body_p("The unit and invariant test suites run with pytest-randomly enabled by default. Every run randomizes test order to detect state leakage between test fixtures. If a test fails under a specific seed, the seed is printed to allow exact reproduction. Only the integration suite opts out of randomization due to sequential database table creation.")

    h2("3.3 Deterministic Echo Provider vs Live Evaluation")
    body_p("CI pipelines execute in under 4 minutes because all unit and integration tests use EchoProvider. EchoProvider returns pre-recorded model responses and explicitly raises NoFixtureError when an unexpected call is made. This guarantees that test suites never make unmocked network calls and that test coverage cannot quietly pass when code paths deviate.")

    # ==========================================
    # 4. FUNCTIONAL TEST CASES
    # ==========================================
    h1("4. Functional Test Cases")
    body_p("Below is a representative sample of official functional test cases executed across the intelligence pipeline and integration boundaries:")

    tc_func_data = [
        ["TC-F01", "Intent Parsing", "Natural language query entered.", "Parse objective into structured Operations and Targets.", "Intent contains correct operation list (READ, COMPARE) and identified document names.", "PASS"],
        ["TC-F02", "Task DAG Compilation", "Valid intent with 3 documents.", "Generate execution plan tree and dependency waves.", "Acyclic DAG produced; document read tasks scheduled in parallel wave 0.", "PASS"],
        ["TC-F03", "Deterministic Routing", "Task requires CSV parsing.", "Evaluate candidate tools against operation.", "CsvParserTool selected without invoking LLM tie-breaker.", "PASS"],
        ["TC-F04", "Wave Execution", "3 tasks in Wave 0.", "Execute tasks concurrently via asyncio.gather.", "All 3 tasks complete within wave bounds; observations merged into context.", "PASS"],
        ["TC-F05", "Locator Resolution", "Model emits reference 'report.txt:r14'.", "Resolve reference against parsed document line index.", "Locator resolves to ExactLineLocator(line=14); text matches source verbatim.", "PASS"],
        ["TC-F06", "Negative Case Handling", "Corpus has zero contradictions.", "Execute full investigation pipeline (BUG-005).", "Relevance Gate filters restatements; engine returns exactly 0 findings.", "PASS"],
        ["TC-F07", "Adaptive Replanning", "Gap detector finds missing financial doc.", "Trigger replan controller during run.", "New task dynamically inserted into active plan; executed in next wave.", "PASS"],
        ["TC-F08", "Composite Verification", "Candidate finding claims date mismatch.", "Pass claim to independent CompositeVerifier.", "Lexical verifier checks tokens; model verifier validates claim against evidence.", "PASS"],
        ["TC-F09", "Multimodal OCR", "Scanned PDF image uploaded.", "Invoke RapidOCR via PdfReaderTool.", "Text correctly extracted from image; page locators assigned (scan.pdf:p1).", "PASS"],
        ["TC-F10", "Speech-to-Text", "Audio recording (.wav) supplied.", "Execute audio transcription tool.", "Audio transcribed into text with segment timestamp locators.", "PASS"],
        ["TC-F11", "Conflict Detection", "Document A: 2024; Document B: 2025.", "Analyze temporal statements in knowledge graph.", "Flagged as CONTRADICTION; evidence links both source locators.", "PASS"],
        ["TC-F12", "Custody Hash Integrity", "Evidence item ingested.", "Compute SHA-256 hash and query /verify.", "Computed hash matches stored hash; status returns INTEGRITY_OK.", "PASS"],
        ["TC-F13", "Prompt Injection Defense", "Document contains 'Ignore instructions'.", "Ingest text wrapped in untrusted boundary.", "SecurityScanner flags injection; text treated as data, instructions ignored.", "PASS"],
        ["TC-F14", "SSE Event Stream", "Mission started via POST /api/v1/missions.", "Subscribe to /api/v1/missions/{id}/events.", "SSE stream pushes RUN_STARTED, TASK_DISPATCHED, and REPORT_SYNTHESIZED.", "PASS"],
        ["TC-F15", "3D Graph Sync", "Mission extracts 20 entities, 15 claims.", "Query GET /api/v1/missions/{id}/knowledge.", "Returns structured node/link graph; loads into Three.js force explorer.", "PASS"]
    ]
    styled_table(["Test ID", "Feature / Component", "Preconditions / Input", "Test Steps / Action", "Expected Result", "Status"], tc_func_data, [0.6, 1.2, 1.3, 1.4, 1.5, 0.5])

    # ==========================================
    # 5. NON-FUNCTIONAL TEST CASES
    # ==========================================
    h1("5. Non-Functional Test Cases")
    body_p("Non-functional testing evaluates the performance, stability, boundary ceilings, security posture, and resilience of the architecture:")

    tc_nfunc_data = [
        ["TC-NF01", "Loop Bounds (Invariant 7)", "Mock engine simulating endless replanning.", "Enforce MAX_REPLAN_ITERATIONS=3 limit.", "Loop terminates after 3 iterations; REPLAN_LIMIT_REACHED event logged.", "PASS"],
        ["TC-NF02", "LLM Isolation (Invariant 1)", "AST scan of entire backend repository.", "Check for httpx/requests/ollama calls outside app/llm.", "Zero external imports found outside provider module.", "PASS"],
        ["TC-NF03", "Run Wallclock Timeout", "Task configured with simulated 700s delay.", "Execute mission with RUN_WALLCLOCK_LIMIT_S=600.", "Execution aborted at 600s; partial results safely checkpointed.", "PASS"],
        ["TC-NF04", "Deliberation Redaction", "Model response contains thinking: '...' field.", "Capture event bus payloads sent to database and SSE.", "Thinking field stripped; REDACTED_PAYLOAD_KEYS applied.", "PASS"],
        ["TC-NF05", "Air-Gapped Offline Operation", "Disconnect all host network interfaces.", "Execute healthcheck.py and complete live investigation.", "100% offline completion; local Ollama, PostgreSQL, and Neo4j function.", "PASS"],
        ["TC-NF06", "Custody Trigger Immutability", "Direct SQL query: UPDATE custody_events SET ...", "Attempt modification of custody table.", "PostgreSQL trigger raises EXCEPTION; modification rejected.", "PASS"],
        ["TC-NF07", "Windows Character Encoding", "Console set to cp1252; output Unicode symbols.", "Run CLI healthcheck and report renderers (BUG-001).", "All console output strictly ASCII-safe; zero UnicodeEncodeError.", "PASS"],
        ["TC-NF08", "Deterministic Repetition", "Execute investigation 3 times with seed=42.", "Compare findings, tool choices, and task graphs.", "Identical graph topologies and findings across all 3 runs.", "PASS"],
        ["TC-NF09", "Frontend Bundle Optimization", "Execute npm run build in frontend directory.", "Measure total chunk size including 3D Three.js bundle.", "Single vendor bundle < 1.6 MB gzip; builds in under 16 seconds.", "PASS"],
        ["TC-NF10", "Database Connection Resilience", "Stop Neo4j container while starting mission.", "Execute mission requiring graph extraction.", "Graceful fallback to MemoryGraphStore; logged graph_store_degraded.", "PASS"]
    ]
    styled_table(["Test ID", "Category", "Preconditions / Input", "Test Steps / Action", "Expected Result", "Status"], tc_nfunc_data, [0.6, 1.2, 1.3, 1.4, 1.5, 0.5])

    # ==========================================
    # 6. BUGS AND FIXES
    # ==========================================
    h1("6. Bugs and Architectural Fixes")
    body_p("Over 41 major defects were cataloged, root-caused, and architecturally resolved during system development. Rather than patching symptoms, fixes addressed systemic patterns. Below is an exhaustive breakdown of key architectural bugs:")

    bugs_data = [
        ["BUG-001", "Windows CP1252 Crash", "Unicode arrows (->) in console healthcheck caused UnicodeEncodeError on Windows terminals.", "Enforced strict ASCII-only rendering across all CLI, logging, and evaluation entry points."],
        ["BUG-002", "JSON Array Delimiter Trap", "Balanced delimiter parser scanned '{' before '[', truncating candidate JSON arrays to the first item.", "Updated parser to lock onto whichever delimiter '{' or '[' appears first in text."],
        ["BUG-003", "Qwen3 Reasoning Token Exhaustion", "Reasoning model spent entire output token budget on 'thinking' field, returning empty responses.", "Passed think: false by default and isolated model deliberation from response payload."],
        ["BUG-004", "Citation Regex Trailing Prose", "Model added trailing explanations to locators (doc.txt:r7: text), failing rpartition(':').", "Engineered anchored regex _LOCATOR matching prefix reference and ignoring trailing text."],
        ["BUG-005", "Negative Case Confabulation", "Model invented 8 contradiction findings on consistent documents because restatements passed verification.", "Introduced the Relevance Gate and structural rule: conflict claims must cite multiple sources."],
        ["BUG-013", "Invisible Replan Tasks", "Tasks inserted dynamically by replanning were missing from UI task view and event streams.", "Bound inserted tasks to the parent PlanTree with explicit REPLAN_TASK_INSERTED events."],
        ["BUG-018", "Verifier Hallucination Approval", "Model verifier approved a claim containing a date not present in the cited evidence.", "Added CompositeVerifier combining lexical n-gram token overlap with model verification."],
        ["BUG-021", "Shipment Number Date Confusion", "Verifier accepted 'delivered on 9012' taking a shipment ID for a calendar date.", "Implemented semantic date pattern validators within the verification token pipeline."],
        ["BUG-025", "Audio Transcribe PyAV Disagreement", "faster-whisper and PyAV 19 disagreed on audio stream formats, failing all transcription.", "Standardized on explicit PCM float32 stream normalization prior to feeding Whisper."],
        ["BUG-030", "Risk vs Contradiction Loss", "Questions asking for risks as well as contradictions dropped valid single-source facts.", "Created distinct statement classifications: single-source findings labelled FACT, conflicts CONTRADICTION."],
        ["BUG-033", "False Contradictions on Semantic Descriptions", "Differing verbal descriptions of the same attribute were incorrectly flagged as contradictions.", "Separated DIFFERING_DESCRIPTIONS from true CONTRADICTIONS in the knowledge graph schema."],
        ["BUG-034", "Knowledge Pass Skew", "Knowledge extraction loop read chunks from the first document only, ignoring remaining files.", "Implemented proportional fair-share chunk allocation across all ingested case documents."],
        ["BUG-035", "Incomplete Plan Early Abort", "Planner omitted a required intermediate operation, failing the mission before reading a line.", "Added automated terminal-task repair to append missing synthetic collection tasks."],
        ["BUG-036", "Whitespace in Document Locators", "Citations referencing documents with spaces (e.g. Project Report.pdf) failed locator resolution.", "Updated locator parser to support quoted and escaped document filenames in references."],
        ["BUG-041", "Frontend Limitations Type Mismatch", "Frontend typed report limitations as plain strings; backend emitted structured Limitation objects.", "Synchronized TypeScript interface with Pydantic schema including cause, impact, and severity."]
    ]
    styled_table(["Bug ID", "Defect Title", "Root Cause & Symptom", "Architectural Resolution"], bugs_data, [0.7, 1.5, 2.3, 2.0])

    # ==========================================
    # 7. TESTING TOOLS USED
    # ==========================================
    h1("7. Testing Tools Used")
    body_p("The project employs a robust toolchain spanning unit testing, static linting, type validation, adversarial scanning, and automated evaluation harnesses:")

    tool_data = [
        ["Pytest & Pytest Plugins", "pytest 9.1, pytest-asyncio, pytest-cov, pytest-randomly", "Core testing framework. Executes 1,036+ tests in randomized order to prevent state leakage; generates branch coverage metrics."],
        ["Static Linters & Type Checkers", "Ruff 0.17, Mypy 2.4 (strict mode)", "Ruff enforces PEP 8, import sorting, and security lints. Mypy enforces strict static typing across all Pydantic boundary models."],
        ["Evaluation Harness", "app.cli eval, check_eval_reports.py", "Automated benchmarking suite running 14 real-world scenarios. Evaluates citation accuracy, evidence coverage, and hallucination rates."],
        ["Frontend Testing Suite", "Vitest 5.0, TypeScript compiler (tsc)", "Executes frontend unit tests, validates Three.js graph transformations, and verifies zero TypeScript compiler errors (--noEmit)."],
        ["Adversarial Security Tools", "SecurityScanner, STIX MITRE ATT&CK", "Custom prompt-injection evaluation dataset (27 attack vectors) and STIX 2.1 threat taxonomy validator."],
        ["Infrastructure Harness", "Docker Compose, Alembic, healthcheck.py", "Manages database containers, applies schema migrations head-to-head, and performs pre-flight system readiness checks."]
    ]
    styled_table(["Tool Name", "Version / Package", "Operational Role in Quality Assurance"], tool_data, [1.4, 1.8, 3.3])

    # ==========================================
    # 8. PROJECT SCHEDULE & PHASES
    # ==========================================
    h1("8. Project Schedule & Milestones")
    body_p("The project followed an agile, phase-driven delivery schedule consisting of 55 distinct engineering increments across 6 core tracks:")

    schedule_data = [
        ["Track 1: Core Intelligence Engine", "Phases 0–18\n(Sept 23 – Oct 01)", "Foundational schemas, LLM provider, prompt library, intent parsing, DAG planning, tool router, wave execution, reasoning, relevance gate, and report synthesis."],
        ["Track 2: API, UI & Hardening", "Phases 19–24\n(Oct 01 – Oct 03)", "FastAPI REST endpoints, Server-Sent Events (SSE), React Mission Control UI, interactive replay journal, adversarial test suite, and CI workflows."],
        ["Track 3: In-Process Teammate Port", "Phases 25–35\n(Oct 03 – Oct 05)", "Porting Member 3 (Knowledge Graph, Neo4j, 3D explorer) and Member 4 (Lexical verifier, Prompt injection scanner, 3-tier episodic memory) in-process."],
        ["Track 4: Multimodal Ingestion", "Phases 36–42\n(Oct 05 – Oct 06)", "RapidOCR for scanned PDFs/images, faster-whisper for audio, OpenCV + Qwen2.5-VL for video frames, and stored semantic retrieval (M2Context)."],
        ["Track 5: Platform v2 (Cases & Evidence)", "Phases 43–53\n(Oct 07 – Oct 12)", "Evidence Locker, chain of custody, case management, statement authority, MITRE ATT&CK mapping, human review lifecycle, and PDF/DOCX exporters."],
        ["Track 6: Enterprise & Final Handover", "Phases 54–55\n(Oct 13+)", "Enterprise RBAC role matrix, air-gapped security policies, academic defense deliverables, and benchmark reproducibility packaging."]
    ]
    styled_table(["Track / Milestone", "Phases & Timeline", "Key Deliverables & Architectural Output"], schedule_data, [1.5, 1.3, 3.7])

    # ==========================================
    # 9. GRAPHICAL USER INTERFACE (GUI)
    # ==========================================
    h1("9. Graphical User Interface (GUI)")
    body_p("The frontend is built as a single-page application using React 19, TypeScript, Vite, and a custom vanilla CSS design system. It eschews generic dashboard templates in favor of a specialized investigation workbench:")

    h2("9.1 Core Interactive Views")
    gui_data = [
        ["1. Cases Dashboard (#/cases)", "Investigation management interface. Groups missions into formal forensic cases, tracks assigned evidence items, and provides quick case creation."],
        ["2. Live Mission Control (#/missions/:id)", "Real-time orchestration cockpit. Displays streaming task DAGs, active wave progress, parallel tool dispatches, and interim findings over SSE."],
        ["3. 3D Knowledge Explorer (#/knowledge)", "Interactive 3D force-directed graph (Three.js / 3d-force-graph). Explores entity clusters, relationship links, temporal claims, and cross-document conflicts."],
        ["4. Evidence Locker (#/evidence)", "Digital chain-of-custody vault. Displays SHA-256 integrity checksums, file parsers, custody audit timelines, and direct links to supported findings."],
        ["5. Document Repository (#/documents)", "Workspace file manager. Displays file formats, chunk boundaries, parser assignments, and semantic vector search with hit highlighting."],
        ["6. Cross-Mission Memory (#/memory)", "Long-term episodic and entity memory viewer. Allows analysts to browse learned facts, past investigation summaries, and entity dossiers."],
        ["7. Cyber Threat Graph (#/missions/:id/cyber)", "MITRE ATT&CK threat mapping interface. Visualizes tactics, techniques, detection rules, and incident killchains derived from security event logs."],
        ["8. Replay Journal (#/replay)", "Deterministic investigation time machine. Replays past recorded missions step-by-step at up to 20x speed for audit, review, and presentation."],
        ["9. Evaluation & Trust Dashboard (#/evaluation)", "Benchmark visualization console. Charts precision, recall, hallucination rate, and task efficiency across committed evaluation runs."]
    ]
    styled_table(["GUI Screen", "Description & Operational Capabilities"], gui_data, [1.8, 4.7])

    h2("9.2 UI Design Principles & Accessibility")
    bullet_p("Dark/Light Mode Theme Tokens: Built using curated HSL color tokens with high-contrast accessibility standards.", "Visual Design: ")
    bullet_p("Dual Mission Perspective: Toggle between 'Professional View' (plain-language summaries and verdicts for executives) and 'Technical Trace' (granular DAG states, locators, and tool payloads for forensic analysts).", "Perspective Toggle: ")
    bullet_p("Reduced Motion Support: 3D force graphs automatically fall back to 2D canvas layouts when users have OS reduced-motion preferences enabled.", "Motion Accessibility: ")
    bullet_p("Direct Evidence Highlighting: Clicking any citation link immediately shifts focus to the exact document line in the Evidence Locker with cryptographic proof.", "Forensic Traceability: ")

    # Save document
    output_path = os.path.abspath("JARVIS_Comprehensive_Engineering_Report.docx")
    doc.save(output_path)
    print(f"Report generated successfully at: {output_path}")

if __name__ == "__main__":
    build_report()
