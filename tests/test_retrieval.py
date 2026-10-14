from datetime import UTC, datetime, timedelta

from rag.index.vector_store import Hit, SearchFilters
from rag.retrieval.query import plan_query
from rag.retrieval.retriever import Retriever, recency_score

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def test_glossary_expansion():
    plan = plan_query("What did the FOMC minutes say?", NOW)
    assert "Federal Open Market Committee" in plan.search_text
    # already spelled out -> no duplicate expansion
    assert "(" not in plan_query("What did the Bank of England (BoE) decide?", NOW).search_text.split("?")[1]


def test_market_region_and_time_sensitivity():
    plan = plan_query("How did the KSE-100 do this week?", NOW)
    assert plan.filters.markets == ["psx"]
    assert plan.region == "pk"
    assert plan.time_sensitive
    assert plan.filters.since == NOW - timedelta(days=7)


def test_month_sets_start_only_and_may_needs_year():
    plan = plan_query("Summarise the ECB September meeting", NOW)
    assert plan.filters.since == datetime(2026, 9, 1, tzinfo=UTC)
    assert plan.filters.until is None  # accounts are published weeks after the meeting
    assert plan_query("Bitcoin may rise", NOW).filters.since is None
    assert plan_query("What happened in May 2026?", NOW).filters.since == datetime(2026, 5, 1, tzinfo=UTC)


def test_last_n_days():
    assert plan_query("BTC news in the last 3 days", NOW).filters.since == NOW - timedelta(days=3)


def test_recency_half_life():
    assert recency_score(NOW.timestamp(), NOW.timestamp(), 7) == 1.0
    assert abs(recency_score((NOW - timedelta(days=7)).timestamp(), NOW.timestamp(), 7) - 0.5) < 1e-9


# --- Retriever with fakes: no models, so the ranking logic itself is tested ---

def _hit(i: int, doc: str, age_days: float, region: str = "global") -> Hit:
    ts = NOW - timedelta(days=age_days)
    return Hit(id=str(i), score=1.0, payload={
        "doc_id": doc, "chunk_id": f"{doc}:{i}", "chunk_idx": i, "title": f"title {doc}", "url": "u",
        "publisher": "P", "published_at": ts.isoformat(), "published_ts": ts.timestamp(), "text": f"text {i}",
        "markets": [], "instruments": [], "region": region,
    })


class FakeStore:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    def search(self, query, embedder, mode, filters, limit):
        self.calls.append(filters)
        return self.hits if not (filters.since or filters.markets) else self.hits[:1]


class FakeReranker:
    def __init__(self, scores):
        self.scores = scores

    def score(self, query, passages):
        return self.scores[: len(passages)]


def test_diversity_caps_chunks_per_document():
    hits = [_hit(0, "a", 1), _hit(1, "a", 1), _hit(2, "a", 1), _hit(3, "b", 1)]
    r = Retriever(FakeStore(hits), embedder=object(), reranker=FakeReranker([0.9, 0.8, 0.7, 0.6]))
    docs = [c.payload["doc_id"] for c in r.retrieve("generic question", k=5, now=NOW).chunks]
    assert docs == ["a", "a", "b"]


def test_recency_only_when_question_is_time_sensitive():
    hits = [_hit(0, "old", 60), _hit(1, "new", 0)]
    r = Retriever(FakeStore(hits), embedder=object(), reranker=FakeReranker([0.80, 0.70]))
    assert r.retrieve("what happened to gold prices", now=NOW).chunks[0].payload["doc_id"] == "old"
    assert r.retrieve("latest gold prices", now=NOW).chunks[0].payload["doc_id"] == "new"


def test_region_boost():
    hits = [_hit(0, "global", 1), _hit(1, "pk", 1, region="pk")]
    r = Retriever(FakeStore(hits), embedder=object(), reranker=FakeReranker([0.80, 0.77]))
    assert r.retrieve("rupee outlook", now=NOW).chunks[0].payload["doc_id"] == "pk"


def test_filters_relax_when_too_few_matches():
    store = FakeStore([_hit(i, f"d{i}", 1) for i in range(6)])
    r = Retriever(store, embedder=object(), reranker=FakeReranker([0.5] * 6))
    result = r.retrieve("bitcoin news this week", now=NOW)
    assert len(store.calls) == 3  # filtered -> no date -> no market
    assert len(result.chunks) == 5
    assert any("relaxed" in n for n in result.plan.notes)


def test_ui_filters_override_plan():
    store = FakeStore([_hit(0, "a", 1)])
    Retriever(store, embedder=object(), reranker=FakeReranker([0.5])).retrieve(
        "bitcoin", extra_filters=SearchFilters(markets=["forex"]), now=NOW)
    assert store.calls[0].markets == ["forex"]
