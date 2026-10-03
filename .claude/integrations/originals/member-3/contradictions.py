from collections import defaultdict
from db import get_all

def detect_contradictions():
    claims = get_all("claims")

    # Deduplicate identical claims (same entity, attribute, value, source, page)
    seen = set()
    unique_claims = []
    for c in claims:
        key = (c["entity"], c["attribute"].strip().lower(), c["value"].strip().lower(),
               c["source_document"], c["source_page"])
        if key not in seen:
            seen.add(key)
            unique_claims.append(c)

    grouped = defaultdict(list)
    for c in unique_claims:
        key = (c["entity"].strip().lower(), c["attribute"].strip().lower())
        grouped[key].append(c)

    contradictions = []
    for (entity, attribute), group in grouped.items():
        values = set(c["value"].strip().lower() for c in group)
        if len(values) > 1:
            contradictions.append({
                "entity": entity,
                "attribute": attribute,
                "conflicting_claims": [
                    {"value": c["value"], "source": c["source_document"], "page": c["source_page"]}
                    for c in group
                ]
            })
    return contradictions