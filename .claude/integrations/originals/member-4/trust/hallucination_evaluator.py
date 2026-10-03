"""
trust/hallucination_evaluator.py
Takes a full generated answer (possibly multi-sentence), splits it into
individual claims, verifies each against the evidence pool, and produces
an overall groundedness classification for the whole answer.
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import Claim, Evidence, ClaimStatus
from trust.verifier import verify_claim


def split_into_claims(answer: str) -> list[str]:
    """Naive sentence splitter — good enough for short factual answers."""
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    return [s.strip() for s in sentences if s.strip()]


def evaluate_answer(answer: str, evidence_pool: list[Evidence]) -> dict:
    claim_texts = split_into_claims(answer)
    if not claim_texts:
        return {"overall": ClaimStatus.INSUFFICIENT_EVIDENCE, "claims": []}

    results = []
    for text in claim_texts:
        claim = Claim(text=text)
        result = verify_claim(claim, evidence_pool)
        results.append(result)

    statuses = [r.status for r in results]
    if all(s == ClaimStatus.SUPPORTED for s in statuses):
        overall = ClaimStatus.SUPPORTED
    elif any(s == ClaimStatus.CONTRADICTED for s in statuses):
        overall = ClaimStatus.CONTRADICTED
    elif any(s == ClaimStatus.SUPPORTED for s in statuses):
        overall = ClaimStatus.PARTIALLY_SUPPORTED
    elif all(s == ClaimStatus.INSUFFICIENT_EVIDENCE for s in statuses):
        overall = ClaimStatus.INSUFFICIENT_EVIDENCE
    else:
        overall = ClaimStatus.UNSUPPORTED

    return {
        "overall": overall,
        "claims": [
            {"text": r.claim.text, "status": r.status, "reasoning": r.reasoning}
            for r in results
        ],
    }


if __name__ == "__main__":
    evidence_pool = [
        Evidence(source="incident_report.pdf", page=1, content="Incident occurred at 11:40 AM."),
        Evidence(source="shipping_report.pdf", page=7, content="Shipment 4821 was recorded on 14 September."),
    ]

    # A mixed answer: one true claim, one fabricated/unsupported claim
    answer = ("The incident occurred at 11:40 AM. "
              "The employee responsible was later terminated for misconduct.")

    result = evaluate_answer(answer, evidence_pool)
    print("Overall:", result["overall"])
    for c in result["claims"]:
        print(f"  [{c['status']}] {c['text']}")
        print(f"      -> {c['reasoning']}")
