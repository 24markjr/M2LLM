import re
from db import get_all, find_entity_by_name
import graph as graph_module

def tokenize(text):
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))

def hybrid_search(query: str, depth: int = 1):
    query_tokens = tokenize(query)

    # 1. Entity search — match each significant word in the query, not the whole phrase
    matched_ids = set()
    for token in query_tokens:
        if len(token) < 3:
            continue  # skip tiny/common words
        for e in find_entity_by_name(token):
            matched_ids.add(e["entity_id"])

    # 2. Graph traversal — pull in entities connected to the matched ones
    related_ids = set(matched_ids)
    for eid in matched_ids:
        net = graph_module.get_entity_network(eid, depth=depth)
        if "nodes" in net:
            related_ids.update(n["entity_id"] for n in net["nodes"])

    # 3. Score every claim against the query using explainable factors
    all_claims = get_all("claims")
    results = []
    for c in all_claims:
        score = 0
        reasons = []

        if c["entity"] in matched_ids:
            score += 3
            reasons.append("direct entity match")
        elif c["entity"] in related_ids:
            score += 1
            reasons.append("connected via graph")

        claim_tokens = tokenize(c["attribute"] + " " + c["value"])
        overlap = query_tokens & claim_tokens
        if overlap:
            score += len(overlap)
            reasons.append(f"keyword match: {', '.join(overlap)}")

        if c["source_document"]:
            score += 1
            reasons.append("has source document")

        if score > 0:
            results.append({
                "claim": c,
                "score": score,
                "explanation": reasons
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results