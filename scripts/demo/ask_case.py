"""Ask a question on a case's conversation through the API, timed, and print the answer.

    backend/.venv/Scripts/python scripts/demo/ask_case.py CASE-2026-00166 "question" [language]
"""

from __future__ import annotations

import sys
import time

import httpx

from run_demo_case import BASE, credentials


def main(case_id: str, question: str, language: str = "") -> None:
    client = httpx.Client(base_url=BASE, timeout=900)
    email, password = credentials()
    client.post("/api/v1/auth/login", json={"email": email, "password": password}).raise_for_status()
    started = time.time()
    thread = client.post(
        f"/api/v1/cases/{case_id}/conversation", json={"text": question, "language": language}
    )
    thread.raise_for_status()
    user, answer = thread.json()["turns"][-2:]
    print(f"answered in {time.time() - started:.0f}s")
    if user.get("original_text"):
        print(f"asked: {user['original_text']}\nread in English as: {user['text']}")
    for claim in answer.get("claims", []):
        print(f"  [{claim.get('status') or '-'}] {claim['text']}  {claim.get('citations')}")
    if not answer.get("claims"):
        print("  " + answer["text"])
    if answer.get("translation"):
        print(f"  translation ({answer['translation']['engine']}): {answer['translation']['text']}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
