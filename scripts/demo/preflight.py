"""Pre-flight check before a demonstration: is everything up, warm and on the GPU?

    backend/.venv/Scripts/python scripts/demo/preflight.py

Checks the backend and its model, the databases behind cases and evidence, the console, and that
the model is loaded on the GPU - and warms it with one small call, so the first question asked in
front of an audience is not the one that waits for the model to load. Prints GO or what to fix.
"""

from __future__ import annotations

import json
import time
import urllib.request

import httpx

from run_demo_case import BASE, credentials

OLLAMA = "http://localhost:11434"
CONSOLE = "http://localhost:5173"


def health_ctx() -> int:
    from pathlib import Path

    for line in (Path(__file__).resolve().parents[2] / ".env").read_text("utf-8").splitlines():
        if line.startswith("OLLAMA_NUM_CTX="):
            return int(line.split("=", 1)[1])
    return 11264


def check(name: str, ok: bool, detail: str = "", fix: str = "") -> bool:
    print(f"{'OK  ' if ok else 'FIX '} {name}{f' - {detail}' if detail else ''}")
    if not ok and fix:
        print(f"      -> {fix}")
    return ok


def main() -> None:
    results: list[bool] = []
    client = httpx.Client(base_url=BASE, timeout=30)
    try:
        health = client.get("/health").json()
        results.append(
            check("backend", health.get("status") == "ok", f"model {health.get('model')}",
                  "start Ollama, then the backend (see the runbook)")
        )
    except httpx.HTTPError:
        results.append(check("backend", False, "not reachable on :8000",
                             "start the backend (see the runbook)"))
        return

    email, password = credentials()
    signed = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    results.append(check("sign-in", signed.status_code == 200, email,
                         "check ADMIN_EMAIL / ADMIN_PASSWORD in .env"))
    if signed.status_code == 200:
        stores = client.get("/api/v1/system/stores").json().get("stores", [])
        memory = [s.get("part", "?") for s in stores if s.get("store") == "memory"]
        results.append(check("databases", not memory,
                             "all on Postgres" if not memory else f"in memory: {', '.join(memory)}",
                             "start Docker Desktop, then: docker compose up -d postgres neo4j"))

    started = time.time()
    body = json.dumps({"model": "qwen3:4b", "prompt": "Say OK.", "stream": False, "think": False,
                       "keep_alive": "2h",
                       # The backend's context size, so the warm model is the one it will use.
                       "options": {"num_predict": 3, "num_ctx": health_ctx()}}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{OLLAMA}/api/generate", body, {"Content-Type": "application/json"}), timeout=180).read()
        loaded = json.load(urllib.request.urlopen(f"{OLLAMA}/api/ps"))["models"]
        on_gpu = bool(loaded) and loaded[0]["size_vram"] >= loaded[0]["size"] * 0.98
        results.append(check("model warm", True, f"answered in {time.time() - started:.1f}s, "
                             "kept loaded for 2 hours"))
        results.append(check("model on the GPU", on_gpu,
                             f"{loaded[0]['size_vram'] / 1e9:.2f} of {loaded[0]['size'] / 1e9:.2f} GB"
                             if loaded else "not loaded",
                             "close other GPU programs (games, browsers with video), then rerun"))
    except OSError:
        results.append(check("model", False, "Ollama not reachable on :11434", "start Ollama"))

    try:
        urllib.request.urlopen(CONSOLE, timeout=10)
        results.append(check("console", True, CONSOLE))
    except OSError:
        results.append(check("console", False, f"{CONSOLE} not answering",
                             "cd frontend; npm run dev"))

    print("\nGO" if all(results) else "\nNOT READY - fix the lines marked FIX")


if __name__ == "__main__":
    main()
