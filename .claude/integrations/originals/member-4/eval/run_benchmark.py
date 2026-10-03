"""
eval/run_benchmark.py
Runs the full Member 4 pipeline (verifier + episodic memory) against the
generated benchmark, then prints a metrics dashboard matching the
JARVIS spec's evaluation format.
"""

import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import Claim, Evidence, ClaimStatus
from trust.verifier import verify_claim
from memory.episodic_memory import EpisodicMemory
from security.security_test_suite import run as run_security_suite

DIR = os.path.dirname(os.path.abspath(__file__))


def load_data():
    with open(os.path.join(DIR, "evidence_corpus.json")) as f:
        raw_evidence = json.load(f)
    with open(os.path.join(DIR, "benchmark.json")) as f:
        benchmark = json.load(f)
    evidence_pool = [Evidence(source=e["source"], page=e["page"], content=e["content"]) for e in raw_evidence]
    return evidence_pool, benchmark


def run_benchmark():
    evidence_pool, benchmark = load_data()
    mem = EpisodicMemory(db_path=os.path.join(DIR, "benchmark_run.db"))
    mem.clear()

    results = []
    latencies = []

    for case in benchmark:
        claim = Claim(text=case["claim_text"])
        start = time.perf_counter()
        result = verify_claim(claim, evidence_pool)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        correct = result.status.value == case["expected_status"]
        results.append({**case, "actual_status": result.status.value, "correct": correct})

        mem.log(
            question=case["question"],
            answer=case["claim_text"],
            sources_used=[e.source for e in result.claim.evidence],
            verification_status=result.status.value,
        )

    # --- Aggregate metrics ---
    total = len(results)
    correct = sum(r["correct"] for r in results)
    accuracy = correct / total

    # Hallucination rate: cases that SHOULD have been flagged as risky
    # (CONTRADICTED or INSUFFICIENT_EVIDENCE) but were confidently marked SUPPORTED instead.
    risky_cases = [r for r in results if r["expected_status"] in ("CONTRADICTED", "INSUFFICIENT_EVIDENCE")]
    false_confidence = [r for r in risky_cases if r["actual_status"] == "SUPPORTED"]
    hallucination_rate = len(false_confidence) / len(risky_cases) if risky_cases else 0.0

    by_category = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        by_category[r["category"]]["total"] += 1
        by_category[r["category"]]["correct"] += r["correct"]

    avg_latency = sum(latencies) / len(latencies)

    # --- Security suite (run alongside) ---
    injection_detection_rate = run_security_suite()

    # --- Dashboard ---
    print("\n" + "=" * 60)
    print("JARVIS MEMBER 4 — EVALUATION DASHBOARD")
    print("=" * 60)
    print(f"Total benchmark cases........... {total}")
    print(f"Overall accuracy................ {accuracy:.1%}  ({correct}/{total})")
    print(f"Hallucination rate (false conf.). {hallucination_rate:.1%}  ({len(false_confidence)}/{len(risky_cases)} risky cases)")
    print(f"Avg verification latency........ {avg_latency:.2f} ms")
    print(f"Injection detection rate........ {injection_detection_rate:.1%}")
    print("-" * 60)
    print("Accuracy by category:")
    for cat, stats in by_category.items():
        acc = stats["correct"] / stats["total"]
        print(f"  {cat:<22} {stats['correct']:>3}/{stats['total']:<3}  ({acc:.1%})")
    print("=" * 60)

    if false_confidence:
        print("\nCases where verifier was falsely confident (needs attention):")
        for r in false_confidence[:5]:
            print(f"  - [{r['expected_status']} -> {r['actual_status']}] {r['claim_text']}")

    print(f"\n{len(mem.all_entries())} verification runs logged to episodic memory "
          f"({os.path.join(DIR, 'benchmark_run.db')}).")

    return {
        "accuracy": accuracy,
        "hallucination_rate": hallucination_rate,
        "avg_latency_ms": avg_latency,
        "injection_detection_rate": injection_detection_rate,
        "category_scores": {k: v["correct"] / v["total"] for k, v in by_category.items()},
    }


if __name__ == "__main__":
    run_benchmark()
