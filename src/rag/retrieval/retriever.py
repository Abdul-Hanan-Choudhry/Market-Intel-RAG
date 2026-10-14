"""The full retrieval pipeline used by the LLM, the API and the evaluation:

    question
      -> plan_query          markets / dates / region / instruments from the text
      -> hybrid search       BM25 + dense, fused with RRF, top N candidates (filtered)
      -> relax if too few    drop the date filter, then the market filter
      -> rerank              cross-encoder relevance probability per candidate
      -> boost               + recency (news decays) + region/instrument match
      -> diversify           at most K chunks per document
      -> top k
"""

import math
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from rag.config import settings
from rag.index.embedder import Embedder, get_embedder
from rag.index.vector_store import Hit, SearchFilters, SearchMode, VectorStore
from rag.retrieval.query import QueryPlan, plan_query
from rag.retrieval.reranker import Reranker, get_reranker

MIN_CANDIDATES = 4


@dataclass
class RetrievedChunk:
    hit: Hit
    relevance: float
    recency: float
    boost: float
    score: float

    @property
    def payload(self) -> dict:
        return self.hit.payload

    def to_dict(self) -> dict:
        p = self.payload
        return {
            "chunk_id": p["chunk_id"], "doc_id": p["doc_id"], "title": p["title"], "url": p["url"],
            "publisher": p["publisher"], "published_at": p["published_at"], "markets": p["markets"],
            "section": p.get("section"), "text": p["text"],
            "relevance": round(self.relevance, 4), "recency": round(self.recency, 4), "score": round(self.score, 4),
        }


@dataclass
class RetrievalResult:
    plan: QueryPlan
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, float] = field(default_factory=dict)
    n_candidates: int = 0

    @property
    def best_relevance(self) -> float:
        return max((c.relevance for c in self.chunks), default=0.0)


@dataclass
class RetrieverConfig:
    mode: SearchMode = "hybrid"
    use_plan: bool = True
    rerank: bool = True
    recency: bool = True
    diversify: bool = True
    candidates: int = settings.rerank_candidates
    max_per_doc: int = settings.max_chunks_per_doc


def rerank_text(p: dict) -> str:
    return f"{p['title']} | {p['publisher']}, {p['published_at'][:10]}\n{p['text']}"


def recency_score(published_ts: float, now: float, half_life_days: float) -> float:
    age_days = max(0.0, (now - published_ts) / 86400)
    return math.exp(-math.log(2) * age_days / half_life_days)


class Retriever:
    def __init__(self, store: VectorStore | None = None, embedder: Embedder | None = None,
                 reranker: Reranker | None = None):
        self.store = store or VectorStore()
        self.embedder = embedder or get_embedder()
        self._reranker = reranker

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            self._reranker = get_reranker()
        return self._reranker

    def _search(self, plan: QueryPlan, cfg: RetrieverConfig) -> list[Hit]:
        def run(filters: SearchFilters) -> list[Hit]:
            return self.store.search(plan.search_text, self.embedder, mode=cfg.mode,
                                     filters=filters, limit=cfg.candidates)

        filters = plan.filters
        hits = run(filters)
        # Filters come from heuristics; if they starve the search, relax them step by step.
        if len(hits) < MIN_CANDIDATES and (filters.since or filters.until):
            filters = replace(filters, since=None, until=None)
            plan.notes.append("relaxed date filter (too few matches)")
            hits = run(filters)
        if len(hits) < MIN_CANDIDATES and filters.markets:
            filters = replace(filters, markets=[])
            plan.notes.append("relaxed market filter (too few matches)")
            hits = run(filters)
        return hits

    def retrieve(self, question: str, k: int = 5, config: RetrieverConfig | None = None,
                 extra_filters: SearchFilters | None = None, now: datetime | None = None) -> RetrievalResult:
        cfg = config or RetrieverConfig()
        now = now or datetime.now(UTC)
        timings: dict[str, float] = {}

        t = time.perf_counter()
        plan = plan_query(question, now) if cfg.use_plan else QueryPlan(question=question, search_text=question)
        if extra_filters:  # explicit UI filters win over heuristics
            for name in ("markets", "instruments", "sources", "doc_types", "since", "until"):
                if value := getattr(extra_filters, name):
                    setattr(plan.filters, name, value)
        hits = self._search(plan, cfg)
        timings["search"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        if cfg.rerank and hits:
            relevance = self.reranker.score(plan.search_text, [rerank_text(h.payload) for h in hits])
        else:  # without a reranker, fall back to a rank-based score so boosts stay comparable
            relevance = [1 / (1 + i) for i in range(len(hits))]
        timings["rerank"] = (time.perf_counter() - t) * 1000

        # Measured in eval: a blanket recency boost pushed older-but-correct answers down, so
        # freshness only counts when the question asks for it ("latest", "today", "this week").
        recency_w = settings.recency_weight if plan.time_sensitive else 0.0
        scored: list[RetrievedChunk] = []
        for hit, rel in zip(hits, relevance):
            p = hit.payload
            rec = recency_score(p["published_ts"], now.timestamp(), settings.recency_half_life_days)
            boost = 0.0
            if plan.region and p.get("region") == plan.region:
                boost += 0.05
            if plan.instruments and set(plan.instruments) & set(p.get("instruments", [])):
                boost += 0.05
            score = rel + (recency_w * rec if cfg.recency else 0.0) + boost
            scored.append(RetrievedChunk(hit, rel, rec, boost, score))
        scored.sort(key=lambda c: c.score, reverse=True)

        if cfg.diversify:
            per_doc: dict[str, int] = {}
            diverse = []
            for c in scored:
                d = c.payload["doc_id"]
                if per_doc.get(d, 0) < cfg.max_per_doc:
                    diverse.append(c)
                    per_doc[d] = per_doc.get(d, 0) + 1
            scored = diverse

        return RetrievalResult(plan, scored[:k], timings, n_candidates=len(hits))
