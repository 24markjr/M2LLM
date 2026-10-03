"""Answer-level grounding: Member 4's hallucination evaluator, ported.

Ported from `Mem-4/trust/hallucination_evaluator.py`, unchanged in logic. A generated answer is
split into sentences, each sentence is verified on its own against the same evidence, and the
answer is classified from the per-sentence results:

| Per-sentence statuses | Overall |
|---|---|
| all `SUPPORTED` | `SUPPORTED` |
| any `CONTRADICTED` | `CONTRADICTED` |
| any `SUPPORTED` (and none contradicted) | `PARTIALLY_SUPPORTED` |
| all `INSUFFICIENT_EVIDENCE` | `INSUFFICIENT_EVIDENCE` |
| anything else | `UNSUPPORTED` |

The point is the second-to-last row's opposite: an answer with one true sentence and one
invented one is `PARTIALLY_SUPPORTED`, where a score over the whole answer would have averaged
the invention away.
"""

from __future__ import annotations

import re

from app.intelligence.trust.lexical import verify_claim
from app.schemas.trust import AnswerAssessment, EvidenceText, LexicalThresholds, TrustStatus

# The original's sentence splitter: break after . ! or ? followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_into_claims(answer: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(answer.strip()) if s.strip()]


def evaluate_answer(
    answer: str,
    evidence: list[EvidenceText],
    thresholds: LexicalThresholds | None = None,
) -> AnswerAssessment:
    sentences = split_into_claims(answer)
    if not sentences:
        return AnswerAssessment(answer=answer, overall=TrustStatus.INSUFFICIENT_EVIDENCE)

    verdicts = [verify_claim(sentence, evidence, thresholds) for sentence in sentences]
    statuses = [v.status for v in verdicts]

    if all(s is TrustStatus.SUPPORTED for s in statuses):
        overall = TrustStatus.SUPPORTED
    elif any(s is TrustStatus.CONTRADICTED for s in statuses):
        overall = TrustStatus.CONTRADICTED
    elif any(s is TrustStatus.SUPPORTED for s in statuses):
        overall = TrustStatus.PARTIALLY_SUPPORTED
    elif all(s is TrustStatus.INSUFFICIENT_EVIDENCE for s in statuses):
        overall = TrustStatus.INSUFFICIENT_EVIDENCE
    else:
        overall = TrustStatus.UNSUPPORTED

    return AnswerAssessment(answer=answer, overall=overall, claims=verdicts)
