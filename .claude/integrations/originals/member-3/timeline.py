from db import get_all, get_claim
import re
from datetime import datetime

DATE_PATTERNS = ["%d %B", "%d %B %Y", "%B %d", "%B %d, %Y", "%d/%m/%Y", "%d-%m-%Y"]

def try_parse_date(value: str):
    for fmt in DATE_PATTERNS:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(year=2026)  # sample data has no year, assume current
        except ValueError:
            continue
    return None

def build_timeline():
    claims = get_all("claims")
    events = []
    for c in claims:
        if "date" in c["attribute"].lower() or "time" in c["attribute"].lower():
            parsed = try_parse_date(c["value"])
            events.append({
                "claim_id": c["claim_id"],
                "entity": c["entity"],
                "attribute": c["attribute"],
                "value": c["value"],
                "parsed_date": parsed.isoformat() if parsed else None,
                "source": c["source_document"],
                "page": c["source_page"]
            })
    events.sort(key=lambda e: e["parsed_date"] or "9999")

    # add explicit relation-to-previous-event labels
    for i, e in enumerate(events):
        if i == 0:
            e["relation_to_previous"] = None
        else:
            prev = events[i - 1]
            if e["parsed_date"] is None or prev["parsed_date"] is None:
                e["relation_to_previous"] = "UNKNOWN"
            elif e["parsed_date"] == prev["parsed_date"]:
                e["relation_to_previous"] = "SAME_TIME_AS"
            else:
                e["relation_to_previous"] = "AFTER"

    return events

def compare_events(claim_id_a: str, claim_id_b: str):
    """Given two claim IDs, determine their temporal relationship (before/after/same/unknown)."""
    claim_a = get_claim(claim_id_a)
    claim_b = get_claim(claim_id_b)

    if not claim_a or not claim_b:
        return {"error": "one or both claim_ids not found"}

    date_a = try_parse_date(claim_a["value"])
    date_b = try_parse_date(claim_b["value"])

    if not date_a or not date_b:
        return {
            "claim_a": claim_a, "claim_b": claim_b,
            "relation": "UNKNOWN",
            "reason": "could not parse a date from one or both claims"
        }

    if date_a < date_b:
        relation = "A_BEFORE_B"
    elif date_a > date_b:
        relation = "A_AFTER_B"
    else:
        relation = "SAME_TIME"

    return {
        "claim_a": claim_a, "claim_b": claim_b,
        "date_a": date_a.isoformat(), "date_b": date_b.isoformat(),
        "relation": relation
    }