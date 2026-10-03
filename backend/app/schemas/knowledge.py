"""The knowledge layer: entities, how they connect, and what each source claims about them.

Ported from Member 3's knowledge-graph service (`jarvis-member3/schemas.py`, `db.py`), whose
three concepts are kept exactly: an **entity** is a real-world thing, a **relationship** connects
two entities, and a **claim** is one source's assertion of one attribute value about one entity.
See `.claude/integrations/teammate-port.md`, features K1-K14.

What changed in the port is what a claim is tied to. The original recorded a document and a
page. Here every claim carries the same citation string a tool emits (`report.txt:r12`,
`report.pdf:p3`), so a claim the knowledge layer found is something the evidence binder can
resolve, and a reasoning engine can cite it without inventing a locator.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import FrozenModel, JarvisModel, NonEmptyStr


class EntityType(StrEnum):
    """The original's six extraction types, plus OTHER for anything the model labels freely."""

    PERSON = "PERSON"
    ORG = "ORG"
    LOCATION = "LOCATION"
    DATE = "DATE"
    PRODUCT = "PRODUCT"
    SHIPMENT = "SHIPMENT"
    OTHER = "OTHER"


class PartialDate(FrozenModel):
    """A calendar date that may be missing its year or its day.

    The original parsed with `strptime` and then forced every result to 2026 - including dates
    that carried their own year, so "14 September 2025" became 2026. A partial date keeps what
    the source actually said, and comparison treats an unknown field as unknown.
    """

    year: int | None = Field(default=None, ge=1, le=9999)
    month: int = Field(ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)

    def iso(self) -> str:
        """ISO 8601 where possible; `--MM-DD` is the standard form for a date with no year."""
        year = f"{self.year:04d}" if self.year is not None else "-"
        if self.day is None:
            return f"{year}-{self.month:02d}"
        return f"{year}-{self.month:02d}-{self.day:02d}"

    def compatible(self, other: PartialDate) -> bool:
        """Whether the two could be the same date: every field known on both sides agrees."""
        if self.month != other.month:
            return False
        if self.year is not None and other.year is not None and self.year != other.year:
            return False
        return not (self.day is not None and other.day is not None and self.day != other.day)

    @property
    def granularity(self) -> tuple[bool, bool]:
        return (self.year is not None, self.day is not None)


class TimelineRelation(StrEnum):
    """The original's `relation_to_previous` labels, unchanged."""

    SAME_TIME_AS = "SAME_TIME_AS"
    AFTER = "AFTER"
    UNKNOWN = "UNKNOWN"


class ClaimOrder(StrEnum):
    """The original's `/timeline/compare` result labels, unchanged."""

    A_BEFORE_B = "A_BEFORE_B"
    A_AFTER_B = "A_AFTER_B"
    SAME_TIME = "SAME_TIME"
    UNKNOWN = "UNKNOWN"


class ConflictKind(StrEnum):
    """How the conflicting values were compared. Reported so a reader knows what "differ" meant."""

    DATE = "DATE"
    NUMBER = "NUMBER"
    TEXT = "TEXT"


class KnowledgeEntity(JarvisModel):
    """One real-world thing, resolved across every document that mentions it."""

    entity_id: NonEmptyStr
    name: NonEmptyStr
    entity_type: EntityType = EntityType.OTHER
    # Other spellings that resolved to this entity: "Shipment #4821" alongside "Shipment 4821".
    aliases: list[str] = Field(default_factory=list)
    # Citations for every place it was mentioned.
    sources: list[str] = Field(default_factory=list)


class KnowledgeRelationship(JarvisModel):
    """`subject --predicate--> object`, between two resolved entities."""

    relationship_id: NonEmptyStr
    subject_id: NonEmptyStr
    predicate: NonEmptyStr
    object_id: NonEmptyStr
    source: NonEmptyStr


class KnowledgeClaim(JarvisModel):
    """One source's assertion of one attribute value about one entity."""

    claim_id: NonEmptyStr
    entity_id: NonEmptyStr
    attribute: NonEmptyStr
    value: NonEmptyStr
    # The citation, in the form tools emit, so the evidence binder can resolve it.
    source: NonEmptyStr
    document_id: NonEmptyStr
    line: int | None = Field(default=None, ge=1)
    # The source line the value was found on.
    quote: str = ""
    # Whether the value was found in the source text. The model reads a chunk and reports a
    # value; if that value does not appear on any line of the chunk, the model wrote it rather
    # than read it. Ungrounded claims are kept and shown, never used to detect a conflict.
    grounded: bool = True


class ConflictSide(JarvisModel):
    """One of the disagreeing values, with every claim and citation that asserts it."""

    value: NonEmptyStr
    claim_ids: list[str] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class ClaimConflict(JarvisModel):
    """Two or more sources asserting different values for the same attribute of one entity.

    Like the original, it never decides which side is right. It surfaces the disagreement with
    every citation, and judging it is the reasoning engine's and the verifier's job.
    """

    conflict_id: NonEmptyStr
    entity_id: NonEmptyStr
    entity_name: NonEmptyStr
    attribute: NonEmptyStr
    kind: ConflictKind
    sides: list[ConflictSide]

    @model_validator(mode="after")
    def _a_conflict_has_two_sides(self) -> ClaimConflict:
        if len(self.sides) < 2:
            raise ValueError("a conflict needs at least two disagreeing values")
        return self

    @property
    def sources(self) -> list[str]:
        return [source for side in self.sides for source in side.sources]


class TimelineEvent(JarvisModel):
    """A dated claim, placed in order."""

    claim_id: NonEmptyStr
    entity_id: NonEmptyStr
    entity_name: NonEmptyStr
    attribute: NonEmptyStr
    value: NonEmptyStr
    source: NonEmptyStr
    date: PartialDate | None = None
    # True when the year used for ordering was inferred from the other events rather than read
    # from this one. The original assumed 2026 for everything and did not say so.
    year_inferred: bool = False
    relation_to_previous: TimelineRelation | None = None


class ClaimComparison(JarvisModel):
    """The temporal order of two claims."""

    claim_a: KnowledgeClaim
    claim_b: KnowledgeClaim
    date_a: PartialDate | None = None
    date_b: PartialDate | None = None
    relation: ClaimOrder
    reason: str = ""


class NetworkNode(JarvisModel):
    entity_id: NonEmptyStr
    name: NonEmptyStr
    entity_type: EntityType


class NetworkEdge(JarvisModel):
    from_id: NonEmptyStr
    to_id: NonEmptyStr
    predicate: NonEmptyStr
    source: NonEmptyStr


class EntityNetwork(JarvisModel):
    """The neighbourhood of one entity, within `depth` hops in either direction."""

    center_id: NonEmptyStr
    depth: int = Field(ge=0)
    nodes: list[NetworkNode] = Field(default_factory=list)
    edges: list[NetworkEdge] = Field(default_factory=list)


class SearchHit(JarvisModel):
    """A claim ranked by the original's explainable score. Every point has a reason."""

    claim: KnowledgeClaim
    entity_name: str = ""
    score: int = Field(ge=1)
    explanation: list[str] = Field(default_factory=list)


class EntityInvestigation(JarvisModel):
    """Everything known about one entity, in one response.

    The original `/investigation/{name}` endpoint, which its README called the main one.
    """

    entity: KnowledgeEntity
    sources: list[str] = Field(default_factory=list)
    network: EntityNetwork
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    conflicts: list[ClaimConflict] = Field(default_factory=list)


class ExtractionStats(JarvisModel):
    """What building the knowledge base cost and what it could not do.

    Counted, so a knowledge base built from half the documents can never look complete.
    """

    documents: int = Field(default=0, ge=0)
    chunks: int = Field(default=0, ge=0)
    # Chunks over the configured ceiling, not sent to the model.
    chunks_skipped: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    # Chunks whose extraction failed after the structured-output repair budget.
    failed_chunks: int = Field(default=0, ge=0)
    tabular_rows: int = Field(default=0, ge=0)
    claims: int = Field(default=0, ge=0)
    ungrounded_claims: int = Field(default=0, ge=0)
    # Relationships whose subject or object was not an extracted entity, skipped as the
    # original skipped them.
    relationships_skipped: int = Field(default=0, ge=0)
    # Claims past `knowledge.max_claims`, not kept. Counted so a capped knowledge base never
    # looks complete.
    claims_capped: int = Field(default=0, ge=0)
    # Entity names the model returned that appear on no line of their chunk: invented, not read.
    # Measured on Member 3's sample: "Shipment 482:1", from text that says "Shipment 4821".
    entities_ungrounded: int = Field(default=0, ge=0)
    # Identical claims (same entity, attribute, value and citation) stored once.
    duplicate_claims: int = Field(default=0, ge=0)


class KnowledgeSnapshot(JarvisModel):
    """A run's knowledge base. Built once per run and never shared between runs.

    The original kept one SQLite file for every ingest ever made, so a later investigation saw
    an earlier one's contradictions. Here the snapshot belongs to the run that built it.
    """

    entities: list[KnowledgeEntity] = Field(default_factory=list)
    relationships: list[KnowledgeRelationship] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    conflicts: list[ClaimConflict] = Field(default_factory=list)
    stats: ExtractionStats = Field(default_factory=ExtractionStats)
