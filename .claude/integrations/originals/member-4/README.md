# Member 4 — Memory, Trust, Security & Evaluation (Complete Build)

Full implementation of the Member 4 role for the JARVIS/M2LLM project.
Drop this folder's contents into your `m2llm` project root, alongside
your existing `rag/`, `retrieval/`, `llm/` code.

## What's inside

### `schemas.py`
Shared data contracts: `Claim`, `Evidence`, `VerificationResult`, `MemoryEntry`,
`SemanticFact`, `BenchmarkCase`, `EvaluationReport`.

### `memory/` — three-tier memory system
- `working_memory.py` — scratchpad for the CURRENT investigation (objective, plan,
  evidence seen, hypotheses, findings). Snapshot it and archive to episodic memory
  when the investigation ends.
- `episodic_memory.py` — SQLite log of every Q&A interaction + archived investigation
  snapshots, with keyword search over history.
- `semantic_memory.py` — durable subject-predicate-object facts distilled from past
  investigations, with source + confidence.

### `trust/` — verification & hallucination detection
- `verifier.py` — `verify_claim(claim, evidence_pool)`. Uses real TF-IDF cosine
  similarity (scikit-learn, fully offline — no model download needed) to score
  relevance, then applies entity-aware conflict detection: a contradiction requires
  the claim and evidence to share an identifying ID (e.g. a shipment number) but
  disagree on the associated time — not just "any numbers differ," which would
  produce false positives on unrelated facts.
- `hallucination_evaluator.py` — splits a full generated answer into individual
  claims, verifies each independently, and classifies the whole answer as
  SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNSUPPORTED / INSUFFICIENT_EVIDENCE.
  This is what catches an answer that mixes one true fact with one fabricated one.
- `contradiction_test.py` — standalone demo of conflict detection across two documents.

### `security/` — prompt injection defense
- `injection_guard.py` — pattern-based scanner across 5 attack categories (instruction
  override, role manipulation, system-prompt extraction, data exfiltration, tool-call
  spoofing) + `build_safe_prompt()` to wrap all retrieved document content in
  `<document>` tags with an explicit "never obey it" instruction for your prompt builder.
- `security_test_suite.py` — 14-case adversarial battery (11 attacks + 3 clean docs).
  Currently scores 100% detection, 0% false positives.

### `eval/` — the benchmark (Step 6)
- `generate_benchmark.py` — generates a synthetic "incident investigation" dataset:
  **58 evidence documents** covering 40 base facts (people, companies, locations,
  shipment IDs, timestamps, amounts), with ~20% duplicated for confirmation and 25%
  deliberately contradicted across two documents. Produces a **60-case benchmark**
  (30 SUPPORTED, 10 CONTRADICTED, 20 INSUFFICIENT_EVIDENCE). Re-run it any time to
  regenerate a fresh dataset, or increase `n_facts` / `n_insufficient` for a bigger one.
- `evidence_corpus.json`, `benchmark.json` — the generated data.
- `run_benchmark.py` — runs the verifier against every case, logs each run to
  episodic memory, runs the security suite alongside, and prints a full dashboard:
  overall accuracy, hallucination rate (false-confidence on risky cases), per-category
  accuracy, average latency, and injection detection rate.

## Current benchmark results (this run)
```
Overall accuracy................ 100.0%  (60/60)
Hallucination rate (false conf.). 0.0%   (0/30 risky cases)
Avg verification latency........ ~1.8 ms
Injection detection rate........ 100.0%
  supported               30/30   (100.0%)
  insufficient_evidence   20/20   (100.0%)
  contradiction           10/10   (100.0%)
```

## How to wire this into your real ask.py
1. After the LLM generates an answer, run it through `hallucination_evaluator.evaluate_answer()`
   using the same evidence your retriever already pulled — this replaces blind trust in the LLM output.
2. Log every interaction: `EpisodicMemory().log(question, answer, sources_used, verification_status)`.
3. In `rag/prompt_builder.py`, replace raw text concatenation with `build_safe_prompt()`
   from `injection_guard.py` so document content can never be read as an instruction.
4. Periodically distill confirmed facts into `SemanticMemory` for reuse across investigations.
5. Re-run `eval/run_benchmark.py` after any change to `verifier.py` to catch regressions —
   this is exactly how the false-positive bug above was caught and fixed during this build.

## Run everything yourself
    python3 schemas.py
    python3 memory/working_memory.py
    python3 memory/episodic_memory.py
    python3 memory/semantic_memory.py
    python3 trust/verifier.py
    python3 trust/hallucination_evaluator.py
    python3 trust/contradiction_test.py
    python3 security/injection_guard.py
    python3 security/security_test_suite.py
    python3 eval/generate_benchmark.py   # regenerate the dataset
    python3 eval/run_benchmark.py        # full evaluation dashboard
