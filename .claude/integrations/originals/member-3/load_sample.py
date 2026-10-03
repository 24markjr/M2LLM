import json, requests

with open("sample_data.json") as f:
    chunks = json.load(f)

for chunk in chunks:
    resp = requests.post("http://127.0.0.1:8000/ingest", json=chunk)
    print(chunk["source_document"], "->", resp.status_code, resp.json())