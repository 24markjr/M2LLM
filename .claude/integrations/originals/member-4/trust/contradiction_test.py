"""trust/contradiction_test.py — contradiction detection using the upgraded verifier."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import Claim, Evidence
from trust.verifier import verify_claim


def run():
    evidence_pool = [
        Evidence(source="incident_report.pdf", page=1, content="Incident occurred at 11:40 AM."),
        Evidence(source="employee_statement.docx", page=1, content="The incident occurred at 1:15 PM."),
    ]
    claim = Claim(text="The incident occurred at 11:40 AM.")
    result = verify_claim(claim, evidence_pool)
    print(f"Status: {result.status}  (relevance={result.relevance_score:.3f})")
    print(f"Reasoning: {result.reasoning}")
    print("Supporting:", [f"{e.source} p.{e.page}" for e in result.claim.evidence])
    print("Contradicting:", [f"{e.source} p.{e.page}" for e in result.claim.contradicting_evidence])


if __name__ == "__main__":
    run()
