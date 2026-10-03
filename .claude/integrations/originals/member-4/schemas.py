"""
schemas.py — Shared data models for Member 4 (Memory, Trust, Security & Evaluation).
Mirrors team-wide contracts (Claim, Evidence) and adds Member 4's own models.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("EVD"))
    source: str
    page: Optional[int] = None
    content: str
    supports: list[str] = []


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: new_id("CLM"))
    text: str
    status: ClaimStatus = ClaimStatus.UNSUPPORTED
    evidence: list[Evidence] = []
    contradicting_evidence: list[Evidence] = []


class VerificationResult(BaseModel):
    claim: Claim
    status: ClaimStatus
    reasoning: str
    relevance_score: float = 0.0
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: new_id("MEM"))
    investigation_id: Optional[str] = None
    question: str
    answer: str
    sources_used: list[str] = []
    verification_status: Optional[ClaimStatus] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SemanticFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: new_id("FACT"))
    subject: str
    predicate: str
    object: str
    source: str
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BenchmarkCase(BaseModel):
    case_id: str = Field(default_factory=lambda: new_id("BENCH"))
    question: str
    claim_text: str
    expected_status: ClaimStatus
    category: str = "general"


class CategoryScore(BaseModel):
    category: str
    total: int
    correct: int
    accuracy: float


class EvaluationReport(BaseModel):
    total_cases: int
    correct: int
    accuracy: float
    hallucination_rate: float
    avg_latency_ms: float
    category_scores: list[CategoryScore] = []
    injection_detection_rate: float = 0.0


if __name__ == "__main__":
    ev = Evidence(source="incident_report.pdf", page=1, content="Incident occurred at 11:40 AM.")
    claim = Claim(text="The incident occurred at 11:40 AM.", status=ClaimStatus.SUPPORTED, evidence=[ev])
    print(claim.model_dump_json(indent=2))
