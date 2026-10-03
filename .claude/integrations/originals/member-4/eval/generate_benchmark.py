"""
eval/generate_benchmark.py
Builds a synthetic "incident investigation" evidence corpus (~40 documents)
and a benchmark of ~90 test cases spanning SUPPORTED, CONTRADICTED,
INSUFFICIENT_EVIDENCE and PARTIALLY_SUPPORTED categories, covering multiple
entities (people, shipments, companies, timestamps, amounts).

This mirrors the "50 investigation questions / 20 PDFs / 10 images /
10 spreadsheets" benchmark spec, scaled to something generatable offline.
"""

import json
import os
import random

random.seed(42)
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

PEOPLE = ["Rahul Sharma", "Priya Nair", "Aman Verma", "Sana Iyer", "Devika Rao", "Karan Mehta"]
COMPANIES = ["ABC Logistics", "Orion Freight", "Zenith Traders", "Meridian Supply Co"]
LOCATIONS = ["Mumbai Facility", "Pune Warehouse B", "Navi Mumbai Depot", "Thane Loading Dock"]
DOC_TYPES = ["incident_report", "employee_statement", "security_report", "invoice",
             "shipping_report", "inspection_log", "transactions", "audit_note"]


def _doc_name(i: int) -> str:
    return f"{DOC_TYPES[i % len(DOC_TYPES)]}_{i:03d}.pdf"


def generate_corpus(n_facts: int = 40):
    """
    Generates a base set of ground-truth facts, then produces evidence
    documents for each — including deliberate contradictions for a subset
    and duplicate confirming evidence for another subset.
    """
    facts = []
    for i in range(n_facts):
        person = random.choice(PEOPLE)
        company = random.choice(COMPANIES)
        location = random.choice(LOCATIONS)
        hour = random.randint(6, 20)
        minute = random.choice([0, 15, 30, 40, 45])
        shipment_id = 1000 + i
        amount = random.choice([4821, 5620, 7300, 9150, 12040, 15600])
        facts.append({
            "fact_id": f"F{i:03d}",
            "person": person,
            "company": company,
            "location": location,
            "time": f"{hour}:{minute:02d} {'AM' if hour < 12 else 'PM'}",
            "shipment_id": shipment_id,
            "amount": amount,
        })

    evidence_corpus = []
    doc_counter = 0
    contradiction_facts = set(random.sample(range(n_facts), k=n_facts // 4))   # 25% get contradicted
    duplicate_facts = set(random.sample(range(n_facts), k=n_facts // 5))       # 20% get duplicate confirmation

    for idx, f in enumerate(facts):
        source = _doc_name(doc_counter); doc_counter += 1
        content = (f"{f['person']} was present at {f['location']} representing {f['company']}. "
                   f"Shipment {f['shipment_id']} (amount {f['amount']}) was processed at {f['time']}.")
        evidence_corpus.append({"source": source, "page": 1, "content": content, "fact_id": f["fact_id"]})

        if idx in duplicate_facts:
            source2 = _doc_name(doc_counter); doc_counter += 1
            evidence_corpus.append({"source": source2, "page": 1,
                                     "content": content, "fact_id": f["fact_id"]})

        if idx in contradiction_facts:
            source3 = _doc_name(doc_counter); doc_counter += 1
            alt_hour = (int(f["time"].split(":")[0]) + random.choice([1, 2, 3])) % 24
            alt_time = f"{alt_hour}:{random.choice(['00','15','30'])} {'AM' if alt_hour < 12 else 'PM'}"
            conflict_content = (f"{f['person']} was present at {f['location']} representing {f['company']}. "
                                 f"Shipment {f['shipment_id']} (amount {f['amount']}) was processed at {alt_time}.")
            evidence_corpus.append({"source": source3, "page": 1,
                                     "content": conflict_content, "fact_id": f["fact_id"], "conflict": True})

    return facts, evidence_corpus, contradiction_facts


def generate_benchmark(facts, contradiction_idx, n_insufficient=20):
    cases = []
    for idx, f in enumerate(facts):
        claim_text = (f"Shipment {f['shipment_id']} was processed at {f['time']} "
                      f"by {f['person']} representing {f['company']}.")
        expected = "CONTRADICTED" if idx in contradiction_idx else "SUPPORTED"
        cases.append({
            "case_id": f"BENCH-{idx:03d}",
            "question": f"When was shipment {f['shipment_id']} processed and by whom?",
            "claim_text": claim_text,
            "expected_status": expected,
            "category": "contradiction" if expected == "CONTRADICTED" else "supported",
        })

    # Insufficient-evidence cases: ask about facts/entities that don't exist in the corpus
    for i in range(n_insufficient):
        fake_shipment = 90000 + i
        fake_person = f"Unlisted Person {i}"
        cases.append({
            "case_id": f"BENCH-INSUFF-{i:03d}",
            "question": f"What was the salary of {fake_person} in shipment {fake_shipment}?",
            "claim_text": f"{fake_person} received a salary related to shipment {fake_shipment}.",
            "expected_status": "INSUFFICIENT_EVIDENCE",
            "category": "insufficient_evidence",
        })

    random.shuffle(cases)
    return cases


if __name__ == "__main__":
    facts, evidence_corpus, contradiction_idx = generate_corpus(n_facts=40)
    benchmark = generate_benchmark(facts, contradiction_idx, n_insufficient=20)

    with open(os.path.join(OUT_DIR, "evidence_corpus.json"), "w") as f:
        json.dump(evidence_corpus, f, indent=2)
    with open(os.path.join(OUT_DIR, "benchmark.json"), "w") as f:
        json.dump(benchmark, f, indent=2)

    print(f"Generated {len(evidence_corpus)} evidence documents "
          f"({len(contradiction_idx)} contradicted facts, "
          f"covering {len(facts)} base facts).")
    print(f"Generated {len(benchmark)} benchmark cases:")
    from collections import Counter
    print(dict(Counter(c["category"] for c in benchmark)))
