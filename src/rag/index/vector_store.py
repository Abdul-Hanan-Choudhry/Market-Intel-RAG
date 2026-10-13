"""Qdrant collection: one point per chunk, holding a dense vector, a BM25 sparse vector
and a payload (text + metadata) that can be filtered on."""

import atexit
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from qdrant_client import QdrantClient, models

from rag.config import settings
from rag.index.embedder import Embedder

DENSE = "dense"
SPARSE = "bm25"
SearchMode = Literal["dense", "bm25", "hybrid"]

KEYWORD_FIELDS = ("doc_id", "source", "publisher", "doc_type", "region", "markets", "instruments")


def make_client() -> QdrantClient:
    if settings.qdrant_mode == "server":
        return QdrantClient(url=settings.qdrant_url)
    settings.qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(settings.qdrant_path))
    # Local mode holds a file lock; release it before interpreter teardown, not in __del__.
    atexit.register(client.close)
    return client


@dataclass
class SearchFilters:
    markets: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    since: datetime | None = None
    until: datetime | None = None

    def to_qdrant(self) -> models.Filter | None:
        must: list[models.Condition] = []
        for key, values in (("markets", self.markets), ("instruments", self.instruments),
                            ("source", self.sources), ("doc_type", self.doc_types)):
            if values:
                must.append(models.FieldCondition(key=key, match=models.MatchAny(any=values)))
        if self.since or self.until:
            must.append(models.FieldCondition(key="published_ts", range=models.Range(
                gte=self.since.timestamp() if self.since else None,
                lte=self.until.timestamp() if self.until else None,
            )))
        return models.Filter(must=must) if must else None


@dataclass
class Hit:
    id: str
    score: float
    payload: dict

    @property
    def text(self) -> str:
        return self.payload["text"]


class VectorStore:
    def __init__(self, client: QdrantClient | None = None, collection: str | None = None):
        self.client = client or make_client()
        self.collection = collection or settings.qdrant_collection

    def ensure_collection(self, dim: int) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # local mode ignores payload indexes; server mode uses them
            for f in KEYWORD_FIELDS:
                self.client.create_payload_index(self.collection, f, models.PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(self.collection, "published_ts", models.PayloadSchemaType.FLOAT)

    def drop(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)

    def count(self) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, exact=True).count

    def delete_docs(self, doc_ids: list[str]) -> None:
        if doc_ids:
            self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids))]
            )))

    def upsert(self, points: list[models.PointStruct]) -> None:
        self.client.upsert(self.collection, points=points, wait=True)

    def search(self, query: str, embedder: Embedder, mode: SearchMode = "hybrid",
               filters: SearchFilters | None = None, limit: int = 10, prefetch_limit: int = 40) -> list[Hit]:
        dense, sparse = embedder.embed_query(query)
        flt = filters.to_qdrant() if filters else None
        if mode == "dense":
            res = self.client.query_points(self.collection, query=dense, using=DENSE,
                                           query_filter=flt, limit=limit, with_payload=True)
        elif mode == "bm25":
            res = self.client.query_points(self.collection, query=sparse, using=SPARSE,
                                           query_filter=flt, limit=limit, with_payload=True)
        else:
            res = self.client.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(query=dense, using=DENSE, filter=flt, limit=prefetch_limit),
                    models.Prefetch(query=sparse, using=SPARSE, filter=flt, limit=prefetch_limit),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        return [Hit(str(p.id), p.score, p.payload or {}) for p in res.points]
