from pydantic import BaseModel
from typing import Optional, List

class ContextChunk(BaseModel):
    document_id: str
    page: Optional[int] = None
    content: str
    source: str

class Entity(BaseModel):
    entity_id: str
    type: str          # PERSON, ORG, LOCATION, DATE, PRODUCT, etc.
    name: str
    source_document: str
    source_page: Optional[int] = None

class Relationship(BaseModel):
    relationship_id: str
    subject: str        # entity_id
    predicate: str
    object: str          # entity_id or literal value
    source_document: str
    source_page: Optional[int] = None

class Claim(BaseModel):
    claim_id: str
    entity: str
    attribute: str        # e.g. "arrival_date"
    value: str
    source_document: str
    source_page: Optional[int] = None