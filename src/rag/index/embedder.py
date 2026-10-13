"""Dense + sparse encoders, both running on ONNX Runtime via fastembed.

Dense (bge-small-en-v1.5, 384-d): captures meaning -> "OPEC output cut" ~ "oil supply reduction".
Sparse (BM25): one weight per vocabulary term -> exact tickers, numbers, names ("KSE-100", "FOMC").
Queries and documents are encoded differently for BM25: documents get term-frequency
weights, queries just mark which terms are present; Qdrant applies IDF at search time.
"""

from functools import lru_cache

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import models

from rag.config import settings


class Embedder:
    def __init__(self) -> None:
        cache = str(settings.fastembed_cache)
        self.dense = TextEmbedding(settings.embed_model, cache_dir=cache, threads=settings.llm_threads)
        self.sparse = SparseTextEmbedding(settings.sparse_model, cache_dir=cache)
        self.dim = len(next(iter(self.dense.embed(["probe"]))))

    @staticmethod
    def _to_sparse(sv) -> models.SparseVector:
        return models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())

    def embed_documents(self, texts: list[str], batch_size: int = 32
                        ) -> tuple[list[list[float]], list[models.SparseVector]]:
        dense = [v.tolist() for v in self.dense.embed(texts, batch_size=batch_size)]
        sparse = [self._to_sparse(v) for v in self.sparse.embed(texts, batch_size=batch_size)]
        return dense, sparse

    def embed_query(self, query: str) -> tuple[list[float], models.SparseVector]:
        dense = next(iter(self.dense.query_embed(query))).tolist()
        sparse = self._to_sparse(next(iter(self.sparse.query_embed(query))))
        return dense, sparse


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
