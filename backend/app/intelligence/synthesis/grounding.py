"""Checking the report's own prose against its evidence (Phase 37, Member 4's T5).

Synthesis places every number, date and citation from settled state; the model writes two
paragraphs and nothing else (the executive summary and the reasoning). Those two paragraphs are the
only place in a report where a model could still assert something no evidence supports, so they are
checked here, sentence by sentence, with Member 4's answer evaluator as it was ported in Phase 26:

- each sentence is verified on its own against the lines the report's findings cite (their
  `evaluate_answer`, TF-IDF relevance and the conflict rule, no model call);
- each sentence is also checked for **specifics**: a date or figure none of that evidence
  contains, or a number standing where a date belongs (A15, BUG-021). A sentence the lexical check
  supports but that states such a value is reported `PARTIALLY_SUPPORTED`, as the composite
  verifier's rule 4 does for a finding.

The check **reports, it does not rewrite**. The narrative is left as the model wrote it, and the
verdict is attached beside it, so a reader sees both the prose and how far it is grounded.
"""

from __future__ import annotations

from app.intelligence.trust.answer import evaluate_answer, overall_status
from app.intelligence.trust.specifics import numbers_as_dates, ungrounded_specifics
from app.schemas.finding import Finding
from app.schemas.result import NarrativeCheck, SectionKind, SentenceCheck
from app.schemas.trust import EvidenceText, TrustStatus


def evidence_for(findings: list[Finding], evidence_text: dict[str, str]) -> list[EvidenceText]:
    """The lines the report's findings cite, resolved ones only, each once."""
    seen: dict[str, EvidenceText] = {}
    for finding in findings:
        for ref in finding.evidence:
            source = ref.as_ref()
            if ref.is_resolved and source not in seen and source in evidence_text:
                seen[source] = EvidenceText(source=source, content=evidence_text[source])
    return list(seen.values())


def check_narrative(
    section: SectionKind, text: str, evidence: list[EvidenceText]
) -> NarrativeCheck | None:
    """Every sentence of one narrative paragraph, judged against `evidence`. None for no text."""
    if not text.strip():
        return None
    assessment = evaluate_answer(text, evidence)
    sentences: list[SentenceCheck] = []
    for verdict in assessment.claims:
        values = list(
            dict.fromkeys(
                [*ungrounded_specifics(verdict.claim, evidence), *numbers_as_dates(verdict.claim)]
            )
        )
        status = verdict.status
        if status is TrustStatus.SUPPORTED and values:
            status = TrustStatus.PARTIALLY_SUPPORTED
        sentences.append(
            SentenceCheck(
                sentence=verdict.claim,
                status=status,
                reasoning=verdict.reasoning,
                ungrounded=values,
            )
        )
    return NarrativeCheck(
        section=section,
        overall=_overall([s.status for s in sentences]),
        sentences=sentences,
    )


def _overall(statuses: list[TrustStatus]) -> TrustStatus:
    """Member 4's rule, plus one case it never met: a sentence downgraded by the specifics check.

    Their rule maps a lone `PARTIALLY_SUPPORTED` sentence to `UNSUPPORTED` (it only ever saw the
    four statuses a single claim can get). A paragraph whose only flaw is one ungrounded value is
    partly supported, so that case is stated rather than left to fall through.
    """
    if TrustStatus.CONTRADICTED not in statuses and TrustStatus.PARTIALLY_SUPPORTED in statuses:
        return TrustStatus.PARTIALLY_SUPPORTED
    return overall_status(statuses)
