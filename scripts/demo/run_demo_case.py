"""Drive one demonstration investigation through the console's own API, timed.

Signs in (ADMIN_EMAIL / ADMIN_PASSWORD from `.env`, or JARVIS_EMAIL / JARVIS_PASSWORD), opens a
case, uploads the files, asks the question, follows the run and prints each finding with its
verdict - the same path a person takes in the console, so a run made here opens there.

    backend/.venv/Scripts/python scripts/demo/run_demo_case.py vajra
    backend/.venv/Scripts/python scripts/demo/run_demo_case.py clean
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / ".agent" / "fixtures" / "documents"
BASE = os.environ.get("JARVIS_URL", "http://localhost:8000")

CASES = {
    "vajra": {
        "title": "Project VAJRA - thermal imaging sights (supply order VJR/SO/2026/014)",
        "files": [
            "vajra_supply_order.pdf",
            "vajra_invoice_scan.png",
            "vajra_inspection_report.docx",
            "vajra_payment_ledger.xlsx",
            "vajra_committee_minutes_hi.txt",
            "vajra_supplier_call.wav",
        ],
        "question": (
            "Reconcile supply order VJR/SO/2026/014 for thermal imaging sights. Compare the amount "
            "actually paid in the payment ledger with the value of the units accepted in the joint "
            "inspection report, check whether the ledger's payment date came before or after the "
            "inspection report, and compare the delivery date on the invoice with the date the "
            "inspection report records the units as received."
        ),
    },
    "clean": {
        "title": "Project VAJRA batch 2 - thermal imaging sights (supply order VJR/SO/2026/021)",
        "files": [
            "vajra2_supply_order.txt",
            "vajra2_inspection_report.txt",
            "vajra2_payment_ledger.csv",
        ],
        "question": (
            "Audit supply order VJR/SO/2026/021: do the quantity, the amount paid, the payment date "
            "and the inspection record agree with each other and with the order's terms?"
        ),
    },
}


def credentials() -> tuple[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    email = os.environ.get("JARVIS_EMAIL") or env.get("ADMIN_EMAIL", "")
    password = os.environ.get("JARVIS_PASSWORD") or env.get("ADMIN_PASSWORD", "")
    return email, password


def main(name: str) -> None:
    spec = CASES[name]
    client = httpx.Client(base_url=BASE, timeout=900)
    email, password = credentials()
    client.post("/api/v1/auth/login", json={"email": email, "password": password}).raise_for_status()

    case = client.post(
        "/api/v1/cases", json={"title": spec["title"], "severity": "HIGH"}
    ).json()
    case_id = case["case_id"]
    files = [("files", (n, (FIXTURES / n).read_bytes())) for n in spec["files"]]
    started = time.time()
    client.post(f"/api/v1/documents?case={case_id}", files=files).raise_for_status()
    print(f"{case_id}: uploaded {len(files)} files in {time.time() - started:.0f}s")

    started = time.time()
    run = client.post(
        "/api/v1/missions",
        json={"objective": spec["question"], "documents": spec["files"], "case_id": case_id},
    ).json()
    run_id = run["run_id"]
    print(f"run {run_id} started")
    last = ""
    while True:
        detail = client.get(f"/api/v1/missions/{run_id}").json()
        state = f"{detail['status']} / {detail['stage']}"
        if state != last:
            print(f"  {time.time() - started:5.0f}s  {state}")
            last = state
        if detail["status"] not in ("PENDING", "RUNNING", "QUEUED"):
            break
        time.sleep(3)
    print(f"finished in {time.time() - started:.0f}s: {detail['status']}, "
          f"terminated {detail.get('termination_reason')}")
    findings = client.get(f"/api/v1/missions/{run_id}/findings").json().get("findings", [])
    for f in findings:
        verdict = (f.get("verification") or {}).get("status", "NOT_VERIFIED")
        cites = [e["locator"]["document_id"] + ":" + str(e["locator"].get("row") or "")
                 for e in f.get("evidence", []) if e.get("locator")]
        print(f"  {f['finding_id']} [{verdict}] {f['claim']}\n      cites {cites}")
    print(f"open: http://localhost:5173/#/mission/{run_id}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vajra")
