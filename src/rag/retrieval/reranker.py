"""Cross-encoder reranking.

The retriever (bi-encoder) embeds question and passage *separately* and compares
vectors: fast enough to scan the whole index, but it never sees them side by side.
A cross-encoder reads "question [SEP] passage" *together* through every layer, so it
can tell that "FOMC minutes" is answered by "Minutes of the Federal Open Market
Committee" and not by "FOMC statement". It is ~100x more expensive per pair, so we
only run it on the top ~20 candidates.
"""

import math
from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from rag.config import settings


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class Reranker:
    def __init__(self, model: str | None = None):
        self.model = TextCrossEncoder(model or settings.rerank_model,
                                      cache_dir=str(settings.fastembed_cache), threads=settings.llm_threads)

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance probability in [0, 1] for each passage."""
        if not passages:
            return []
        passages = [p[: settings.rerank_max_chars] for p in passages]
        return [sigmoid(s) for s in self.model.rerank(query, passages, batch_size=8)]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
