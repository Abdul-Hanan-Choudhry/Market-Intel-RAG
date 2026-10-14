import threading
from datetime import UTC, datetime

from rag.generation.answer import Answerer, is_refusal, parse_citations
from rag.generation.llm import GenerationStats
from rag.generation.prompt import REFUSAL, SYSTEM_PROMPT, build_messages, pack_sources
from rag.index.vector_store import Hit
from rag.retrieval.query import QueryPlan
from rag.retrieval.retriever import RetrievalResult, RetrievedChunk

NOW = datetime(2026, 10, 13, tzinfo=UTC)


def count(text: str) -> int:
    return len(text.split())


def _chunk(doc: str, idx: int, text: str, relevance: float = 0.9) -> RetrievedChunk:
    payload = {"doc_id": doc, "chunk_id": f"{doc}:{idx}", "chunk_idx": idx, "title": f"Title {doc}",
               "url": f"https://x/{doc}", "publisher": "Dawn", "published_at": "2026-10-12T08:00:00+00:00",
               "text": text, "markets": [], "section": None}
    return RetrievedChunk(Hit(id=f"{doc}{idx}", score=1, payload=payload), relevance, 1.0, 0.0, relevance)


def test_pack_groups_by_document_in_reading_order():
    chunks = [_chunk("a", 3, "later part."), _chunk("b", 0, "other doc."), _chunk("a", 1, "earlier part.")]
    sources = pack_sources(chunks, budget=500, count=count)
    assert [s.doc_id for s in sources] == ["a", "b"]
    assert sources[0].text.index("earlier") < sources[0].text.index("later")
    assert [s.n for s in sources] == [1, 2]


def test_pack_respects_budget():
    long = " ".join(f"Sentence number {i} is here." for i in range(200))
    sources = pack_sources([_chunk("a", 0, long), _chunk("b", 0, long)], budget=150, count=count)
    total = sum(count(s.text) for s in sources)
    assert total <= 150
    assert sources[0].text.endswith("...")


def test_messages_keep_system_prompt_static():
    sources = pack_sources([_chunk("a", 0, "SBP kept the rate at 11%.")], 500, count)
    msgs = build_messages("What did SBP do?", sources, NOW)
    assert msgs[0]["content"] == SYSTEM_PROMPT  # identical every request -> KV cache reuse
    assert "[1] Title a (Dawn, 2026-10-12)" in msgs[1]["content"]
    assert "13 October 2026" in msgs[1]["content"]


def test_parse_citations_and_refusal():
    assert parse_citations("Rate held [1]. Inflation fell [2][3] and [1, 4].") == [1, 2, 3, 4]
    assert parse_citations("no citations") == []
    assert is_refusal(REFUSAL)
    assert not is_refusal("The SBP held rates [1].")


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve(self, question, k, extra_filters=None, now=None):
        return RetrievalResult(QueryPlan(question, question), self.chunks, {"search": 1.0, "rerank": 2.0}, 10)


class FakeLLM:
    name = "fake"

    def __init__(self, reply: str):
        self.reply, self.calls = reply, 0

    def count_tokens(self, text):
        return count(text)

    def stream(self, messages, stats: GenerationStats, max_tokens=None, temperature=None):
        self.calls += 1
        for token in self.reply.split(" "):
            stats.completion_tokens += 1
            yield token + " "


def test_answer_streams_and_validates_citations():
    llm = FakeLLM("SBP kept the policy rate at 11% [1] and later [3].")
    events = list(Answerer(FakeRetriever([_chunk("a", 0, "SBP kept the rate at 11%.")]), llm).stream("q", now=NOW))
    assert events[0]["type"] == "retrieval"
    assert any(e["type"] == "token" for e in events)
    answer = events[-1]["answer"]
    assert answer["cited"] == [1]
    assert answer["invalid_citations"] == [3]
    assert answer["warnings"]
    assert not answer["refused"]


def test_irrelevant_retrieval_refuses_without_calling_llm():
    llm = FakeLLM("should not be called")
    answer = Answerer(FakeRetriever([_chunk("a", 0, "biryani recipe", relevance=0.0001)]), llm).answer("q")
    assert answer["refused"] and llm.calls == 0
    assert answer["answer"] == REFUSAL


class StallingLLM(FakeLLM):
    """Yields one token then hangs forever, simulating a stuck llama.cpp call."""

    def stream(self, messages, stats, max_tokens=None, temperature=None):
        yield "partial "
        stats.completion_tokens += 1
        threading.Event().wait()  # never returns


def test_stall_is_reported_instead_of_hanging_forever():
    from rag import config
    config.settings.llm_stall_timeout_s = 0.3

    events = list(Answerer(FakeRetriever([_chunk("a", 0, "text")]), StallingLLM("")).stream("q", now=NOW))
    assert events[-1]["type"] == "error"
    assert "stuck" in events[-1]["message"]
    assert events[-1]["partial_answer"] == "partial"
    config.settings.llm_stall_timeout_s = 150.0


def test_busy_fails_fast_instead_of_waiting_for_stall_timeout():
    from rag.generation.llm import Busy

    class BusyLLM(FakeLLM):
        def stream(self, messages, stats, max_tokens=None, temperature=None):
            raise Busy("Still answering the previous question (running for 42s).")
            yield  # pragma: no cover - makes this a generator function

    events = list(Answerer(FakeRetriever([_chunk("a", 0, "text")]), BusyLLM("")).stream("q", now=NOW))
    assert events[-1] == {"type": "busy", "message": "Still answering the previous question (running for 42s)."}


def test_model_refusal_is_detected():
    answer = Answerer(FakeRetriever([_chunk("a", 0, "text")]), FakeLLM(REFUSAL)).answer("q", now=NOW)
    assert answer["refused"]
    assert answer["refusal_reason"] == "model found no answer in the sources"
