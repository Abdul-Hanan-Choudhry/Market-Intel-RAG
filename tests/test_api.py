import json

import pytest
from fastapi.testclient import TestClient
from test_generation import FakeLLM, FakeRetriever, _chunk

from rag.api.app import create_app
from rag.generation.answer import Answerer
from rag.ingest.store import Catalog


@pytest.fixture
def client(tmp_path):
    answerer = Answerer(FakeRetriever([_chunk("a", 0, "SBP kept the rate at 11%.")]),
                        FakeLLM("SBP held the policy rate at 11% [1]."))
    app = create_app(answerer=answerer, catalog=Catalog(tmp_path / "c.db"), warmup=False)
    with TestClient(app) as c:
        yield c


def test_health_and_stats(client):
    assert client.get("/health").json()["status"] == "ok"
    stats = client.get("/stats").json()
    assert stats["pipeline"]["documents"] == 0


def test_search(client):
    body = client.post("/search", json={"question": "SBP rate decision"}).json()
    assert body["chunks"][0]["doc_id"] == "a"


def test_ask(client):
    body = client.post("/ask", json={"question": "What did SBP do?", "markets": ["macro"], "days": 7}).json()
    assert body["cited"] == [1]
    assert "11%" in body["answer"]


def test_ask_stream_sse(client):
    with client.stream("POST", "/ask/stream", json={"question": "What did SBP do?"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "retrieval" and types[-1] == "done" and "token" in types
    assert "".join(e["text"] for e in events if e["type"] == "token").strip() == events[-1]["answer"]["answer"]


def test_ask_returns_429_when_busy(tmp_path):
    from rag.generation.llm import Busy

    class BusyLLM(FakeLLM):
        def stream(self, messages, stats, max_tokens=None, temperature=None):
            raise Busy("Still answering the previous question (running for 42s).")
            yield  # pragma: no cover

    app = create_app(answerer=Answerer(FakeRetriever([_chunk("a", 0, "text")]), BusyLLM("")),
                     catalog=Catalog(tmp_path / "c.db"), warmup=False)
    with TestClient(app) as c:
        r = c.post("/ask", json={"question": "What did SBP do?"})
    assert r.status_code == 429


def test_validation(client):
    assert client.post("/ask", json={"question": "x"}).status_code == 422
    assert client.post("/ask", json={"question": "valid question", "k": 50}).status_code == 422
