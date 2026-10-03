import uuid
import db

def resolve_and_store(result: dict, source_document: str, source_page: int = None):
    name_to_id = {}

    for e in result["entities"]:
        entity_id = db.find_or_create_entity(e["name"], e["type"], source_document, source_page)
        name_to_id[e["name"].strip().lower()] = entity_id

    for r in result["relationships"]:
        subject_id = name_to_id.get(r["subject"].strip().lower())
        object_id = name_to_id.get(r["object"].strip().lower())
        if not subject_id or not object_id:
            # one or both endpoints weren't extracted as real entities — skip rather than store garbage
            continue
        db.insert_relationship({
            "relationship_id": f"REL-{uuid.uuid4().hex[:8]}",
            "subject": subject_id,
            "predicate": r["predicate"],
            "object": object_id,
            "source_document": source_document,
            "source_page": source_page
        })

    for c in result["claims"]:
        entity_id = name_to_id.get(c["entity"].strip().lower(), c["entity"])
        db.insert_claim({
            "claim_id": f"CLM-{uuid.uuid4().hex[:8]}",
            "entity": entity_id,
            "attribute": c["attribute"],
            "value": c["value"],
            "source_document": source_document,
            "source_page": source_page
        })