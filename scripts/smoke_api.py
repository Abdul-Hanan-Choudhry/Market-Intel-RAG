"""Smoke-test a running API (`rag serve`): health, stats, and TWO sequential answers
(to specifically verify the busy/lock fix doesn't false-positive on question 2)."""

import json
import time

import httpx

API = "http://127.0.0.1:8000"

print("health:", httpx.get(f"{API}/health").json())
stats = httpx.get(f"{API}/stats").json()
print("stats:", stats["pipeline"], "| newest:", stats["newest_document"])

QUESTIONS = [
    "Which crypto exchanges did Britain sanction over Russia links?",
    "What does the IMF expect for Pakistan's inflation and GDP growth?",
]

for i, q in enumerate(QUESTIONS, 1):
    print(f"\n=== Question {i}: {q} ===")
    t0 = time.perf_counter()
    with httpx.stream("POST", f"{API}/ask/stream", json={"question": q},
                      timeout=httpx.Timeout(10, read=None)) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "retrieval":
                print(f"[{time.perf_counter() - t0:5.1f}s] sources:", [s["title"][:40] for s in event["sources"]])
            elif event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                a = event["answer"]
                print(f"\n[{time.perf_counter() - t0:5.1f}s] cited={a['cited']} warnings={a['warnings']}")
                print("generation:", a["generation"])
            else:
                print("EVENT:", event)
