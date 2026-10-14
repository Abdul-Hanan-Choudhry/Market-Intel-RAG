"""Smoke-test a running API (`rag serve`): health, stats, and one streamed answer."""

import json
import time

import httpx

API = "http://127.0.0.1:8000"

print("health:", httpx.get(f"{API}/health").json())
stats = httpx.get(f"{API}/stats").json()
print("stats:", stats["pipeline"], "| newest:", stats["newest_document"])

t0 = time.perf_counter()
question = {"question": "Which crypto exchanges did Britain sanction over Russia links?"}
with httpx.stream("POST", f"{API}/ask/stream", json=question, timeout=httpx.Timeout(10, read=None)) as r:
    for line in r.iter_lines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if event["type"] == "retrieval":
            print(f"[{time.perf_counter() - t0:5.1f}s] sources:", [s["title"][:50] for s in event["sources"]])
        elif event["type"] == "token":
            print(event["text"], end="", flush=True)
        elif event["type"] == "done":
            a = event["answer"]
            print(f"\n[{time.perf_counter() - t0:5.1f}s] cited={a['cited']} warnings={a['warnings']}")
            print("timings:", a["timings_ms"], "| generation:", a["generation"])
        else:
            print("ERROR:", event)
