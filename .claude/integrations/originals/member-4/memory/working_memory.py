"""
memory/working_memory.py
Scoped, ephemeral memory for the CURRENT investigation only.
Dies (or gets archived into episodic memory) when the investigation ends.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import new_id


class WorkingMemory:
    def __init__(self, investigation_id: str = None, objective: str = ""):
        self.investigation_id = investigation_id or new_id("INV")
        self.objective = objective
        self.plan: list[str] = []
        self.evidence_seen: list[dict] = []
        self.hypotheses: list[str] = []
        self.findings: list[str] = []
        self.started_at = datetime.utcnow()

    def set_plan(self, steps: list[str]):
        self.plan = steps

    def add_evidence(self, source: str, content: str):
        self.evidence_seen.append({"source": source, "content": content})

    def add_hypothesis(self, text: str):
        self.hypotheses.append(text)

    def add_finding(self, text: str):
        self.findings.append(text)

    def snapshot(self) -> dict:
        """Serializable snapshot — used to archive into episodic memory."""
        return {
            "investigation_id": self.investigation_id,
            "objective": self.objective,
            "plan": self.plan,
            "evidence_count": len(self.evidence_seen),
            "hypotheses": self.hypotheses,
            "findings": self.findings,
            "started_at": self.started_at.isoformat(),
        }


if __name__ == "__main__":
    wm = WorkingMemory(objective="Investigate Incident 102")
    wm.set_plan(["process_documents", "extract_entities", "detect_contradictions"])
    wm.add_evidence("incident_report.pdf", "Incident occurred at 11:40 AM.")
    wm.add_hypothesis("Incident time may conflict across sources.")
    wm.add_finding("Two sources disagree on incident time.")
    print(wm.snapshot())
