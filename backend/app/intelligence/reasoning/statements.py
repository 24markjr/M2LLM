"""What kind of statement each finding is (Phase 45).

The review that led to Phase 45 saw every finding labelled FACT. A finding resting on one document
is what that document says - true to its source, uncorroborated - and calling it a fact overstates
it.
The types here are what a reader needs, and they are assigned by rules over the evidence, never by
the model:

- **UNKNOWN** - nothing it cites resolved;
- **HYPOTHESIS** - some of what it cites did not resolve;
- **SOURCE_CLAIM** - everything it cites is in one document;
- **FACT** - two or more documents, every citation resolved, the claim supported (element by
  element, or verified against those lines);
- **INFERENCE** - two or more documents, with a step none of them states outright;
- **CONTRADICTION** - two evidenced values that cannot both be true, cited on both sides.

The model may propose a type (its `classification` field). The stricter of its proposal and the
evidence wins: a model saying FACT over one document gets SOURCE_CLAIM; a model saying HYPOTHESIS
over two agreeing documents gets HYPOTHESIS. It may also propose RISK, RECOMMENDATION or
OBSERVATION, kept when the basis under them is at least an INFERENCE - and the basis is stored
beside it, so a "RISK" is always shown with what it rests on.
"""

from __future__ import annotations

from app.intelligence.trust.specifics import states_two_values
from app.schemas.finding import Finding, FindingClassification, StatementType

# Weakest first. A proposal can move a finding down this list, never up.
EPISTEMIC_ORDER: tuple[StatementType, ...] = (
    StatementType.UNKNOWN,
    StatementType.HYPOTHESIS,
    StatementType.INFERENCE,
    StatementType.SOURCE_CLAIM,
    StatementType.FACT,
)
_RANK = {t: i for i, t in enumerate(EPISTEMIC_ORDER)}

# Kinds a model may propose on top of a supported basis.
PROPOSABLE_KINDS = frozenset(
    {StatementType.RISK, StatementType.RECOMMENDATION, StatementType.OBSERVATION}
)
_SUPPORTED = frozenset({StatementType.FACT, StatementType.SOURCE_CLAIM, StatementType.INFERENCE})

# How models write the types. Anything else is no proposal.
_SYNONYMS: dict[str, StatementType] = {
    "SOURCE CLAIM": StatementType.SOURCE_CLAIM,
    "CLAIM": StatementType.SOURCE_CLAIM,
    "SINGLE SOURCE": StatementType.SOURCE_CLAIM,
    "CONFLICT": StatementType.CONTRADICTION,
    "INCONSISTENCY": StatementType.CONTRADICTION,
    "DISCREPANCY": StatementType.CONTRADICTION,
    "FINDING": StatementType.OBSERVATION,
}


def proposal(raw: str) -> StatementType | None:
    """The type a model's free-text classification names, or None."""
    text = raw.strip().upper().replace("-", " ").replace("_", " ")
    # "UNKNOWN" is the candidate's default - the model said nothing - not a claim of ignorance.
    if not text or text == "UNKNOWN":
        return None
    if text in _SYNONYMS:
        return _SYNONYMS[text]
    try:
        return StatementType(text.replace(" ", "_"))
    except ValueError:
        return None


def basis_of(finding: Finding) -> StatementType:
    """What the evidence alone supports."""
    if finding.resolved_evidence_count == 0:
        return StatementType.UNKNOWN
    if (
        finding.classification is FindingClassification.HYPOTHESIS
        or finding.resolved_evidence_count < len(finding.evidence)
    ):
        return StatementType.HYPOTHESIS
    documents = {e.locator.document_id for e in finding.evidence if e.is_resolved}
    if len(documents) < 2:
        return StatementType.SOURCE_CLAIM
    # Two independent documents, every citation resolved, and the claim either supported element by
    # element or verified against those lines: they agree on it.
    if finding.classification is FindingClassification.FACT or finding.is_verified:
        return StatementType.FACT
    return StatementType.INFERENCE


def is_contradiction(finding: Finding, *, comparative: bool) -> bool:
    """Two different values, both cited and resolved, in a finding that reports a disagreement.

    Reports one when the question asked for a comparison (whose filters already discarded any claim
    stating a value its lines do not hold, BUG-019) or when the finding was proposed as one - by the
    model or by the knowledge graph's conflict (BUG-031). A claim stating one value twice is
    agreement, and is never a contradiction.
    """
    if finding.resolved_evidence_count < 2 or finding.resolved_evidence_count < len(
        finding.evidence
    ):
        return False
    if not states_two_values(finding.claim):
        return False
    return comparative or proposal(finding.proposed_type) is StatementType.CONTRADICTION


def type_statement(finding: Finding, *, comparative: bool) -> tuple[StatementType, StatementType]:
    """`(statement_type, statement_basis)` for a finding whose evidence is final."""
    basis = basis_of(finding)
    if is_contradiction(finding, comparative=comparative):
        return StatementType.CONTRADICTION, basis

    proposed = proposal(finding.proposed_type)
    if proposed in PROPOSABLE_KINDS and basis in _SUPPORTED:
        return proposed, basis
    if proposed in _RANK and _RANK[proposed] < _RANK[basis]:
        # The stricter answer wins. The basis stays what the evidence supports, so the record shows
        # both: the model was more cautious than the evidence required.
        return proposed, basis
    return basis, basis


def type_statements(findings: list[Finding], *, comparative: bool) -> None:
    """Set every finding's statement type in place, once its evidence is final."""
    for finding in findings:
        finding.statement_type, finding.statement_basis = type_statement(
            finding, comparative=comparative
        )
