from datetime import UTC, datetime, timedelta

import pytest
from qdrant_client import QdrantClient

from rag.index import pipeline as indexing
from rag.index.embedder import get_embedder
from rag.index.vector_store import SearchFilters, VectorStore
from rag.ingest.models import DocType, Market, RawDocument
from rag.ingest.store import Catalog
from rag.processing import pipeline as processing

NOW = datetime.now(UTC)

DOCS = [
    ("fed", "Fed holds rates", ("The Federal Reserve held the federal funds rate steady at 4.25 percent, "
     "citing sticky inflation and a resilient labour market."), [Market.MACRO], NOW - timedelta(days=1)),
    ("btc", "Bitcoin ETF inflows", ("Spot bitcoin ETFs recorded their largest weekly inflows this year as "
     "institutional investors added BTC exposure."), [Market.CRYPTO], NOW - timedelta(days=2)),
    ("psx", "KSE-100 closes higher", ("The KSE-100 index of the Pakistan Stock Exchange closed 900 points "
     "higher on buying in cement and banking stocks."), [Market.PSX], NOW - timedelta(days=30)),
]


@pytest.fixture(scope="module")
def indexed(tmp_path_factory):
    cat = Catalog(tmp_path_factory.mktemp("idx") / "c.db")
    for id_, title, text, markets, ts in DOCS:
        cat.upsert(RawDocument(id=id_, source="t", publisher="P", doc_type=DocType.NEWS, url=f"https://x/{id_}",
                               title=title, content=text, published_at=ts, fetched_at=ts, markets=markets))
    processing.run(cat)
    store = VectorStore(client=QdrantClient(":memory:"), collection="test")
    counts = indexing.run(store=store, catalog=cat)
    return cat, store, counts


def test_all_chunks_indexed(indexed):
    cat, store, counts = indexed
    assert counts["indexed_docs"] == 3
    assert store.count() == 3
    assert cat.pending_indexing() == ([], [])


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_search_modes_find_right_doc(indexed, mode):
    _, store, _ = indexed
    hits = store.search("KSE-100 Pakistan stocks", get_embedder(), mode=mode, limit=1)
    assert hits[0].payload["doc_id"] == "psx"


def test_dense_handles_paraphrase(indexed):
    _, store, _ = indexed
    hits = store.search("central bank kept borrowing costs unchanged", get_embedder(), mode="dense", limit=1)
    assert hits[0].payload["doc_id"] == "fed"


def test_filters(indexed):
    _, store, _ = indexed
    emb = get_embedder()
    hits = store.search("market news", emb, filters=SearchFilters(markets=["crypto"]))
    assert {h.payload["doc_id"] for h in hits} == {"btc"}
    recent = store.search("market news", emb, filters=SearchFilters(since=NOW - timedelta(days=7)))
    assert {h.payload["doc_id"] for h in recent} == {"fed", "btc"}


def test_reindex_is_idempotent(indexed):
    cat, store, _ = indexed
    assert indexing.run(store=store, catalog=cat)["indexed_docs"] == 0
    assert store.count() == 3
