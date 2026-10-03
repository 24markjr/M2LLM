import requests, json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

EXTRACTION_PROMPT = """You are an information extraction engine. Given the text below, extract:
1. entities (PERSON, ORG, LOCATION, DATE, PRODUCT, SHIPMENT)
2. relationships between entities (subject, predicate, object)
3. factual claims (entity, attribute, value) — e.g. entity="Shipment 4821", attribute="arrival_date", value="14 September"

Return ONLY valid JSON, no markdown, no explanation, in this exact shape:
{{
  "entities": [{{"type": "...", "name": "..."}}],
  "relationships": [{{"subject": "...", "predicate": "...", "object": "..."}}],
  "claims": [{{"entity": "...", "attribute": "...", "value": "..."}}]
}}

TEXT:
{text}
"""

def extract(text: str) -> dict:
    prompt = EXTRACTION_PROMPT.format(text=text)
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False,
        "format": "json"
    })
    resp_json = resp.json()
    if "response" not in resp_json:
        print("Ollama error:", resp_json)
        return {"entities": [], "relationships": [], "claims": []}
    raw = resp_json["response"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print("Failed to parse model output as JSON:", raw)
        return {"entities": [], "relationships": [], "claims": []}

    entities = [{"type": e.get("type", "UNKNOWN"), "name": e.get("name", "")}
                for e in parsed.get("entities", [])]
    relationships = [{"subject": r.get("subject", ""), "predicate": r.get("predicate", ""),
                       "object": r.get("object", "")} for r in parsed.get("relationships", [])]
    claims = [{"entity": c.get("entity", ""), "attribute": c.get("attribute", ""),
               "value": c.get("value", "")} for c in parsed.get("claims", [])]

    return {"entities": entities, "relationships": relationships, "claims": claims}