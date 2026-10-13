"""Phase 3 pipeline: embed changed chunks and sync them into Qdrant."""

import logging
import time
import uuid
from collections import Counter
from itertools import batched

from qdrant_client import models
from rich.progress import Progress

from rag.config import settings
from rag.index.embedder import get_embedder
from rag.index.vector_store import DENSE, SPARSE, VectorStore
from rag.ingest.models import RawDocument
from rag.ingest.store import Catalog

log = logging.getLogger(__name__)


def point_id(chunk_id: str) -> str:
    # Deterministic: re-indexing the same chunk overwrites its point instead of duplicating it.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def payload(doc: RawDocument, row, n_chunks: int) -> dict:
    return {
        "doc_id": doc.id,
        "chunk_id": row["id"],
        "chunk_idx": row["idx"],
        "n_chunks": n_chunks,
        "text": row["text"],
        "section": row["section"],
        "title": doc.title,
        "url": doc.url,
        "source": doc.source,
        "publisher": doc.publisher,
        "doc_type": doc.doc_type.value,
        "region": doc.region,
        "markets": [m.value for m in doc.markets],
        "instruments": doc.instruments,
        "published_at": doc.published_at.isoformat(),
        "published_ts": doc.published_at.timestamp(),
    }


def run(rebuild: bool = False, batch_docs: int = 16, store: VectorStore | None = None,
        catalog: Catalog | None = None) -> Counter:
    catalog = catalog or Catalog(settings.catalog_path)
    store = store or VectorStore()
    embedder = get_embedder()
    counts: Counter = Counter()

    if rebuild:
        store.drop()
        catalog.reset_index_state()
    store.ensure_collection(embedder.dim)

    to_index, to_remove = catalog.pending_indexing()
    if to_remove:
        store.delete_docs(to_remove)
        catalog.mark_indexed(to_remove, removed=True)
        counts["removed_docs"] = len(to_remove)

    t0 = time.perf_counter()
    with Progress(transient=True) as progress:
        task = progress.add_task("Embedding + indexing", total=len(to_index))
        for batch in batched(to_index, batch_docs):
            batch = list(batch)
            rows = catalog.chunks_for(batch)
            docs = {d: catalog.get_document(d) for d in batch}
            per_doc = Counter(r["doc_id"] for r in rows)
            dense, sparse = embedder.embed_documents([r["embed_text"] for r in rows])
            points = [
                models.PointStruct(
                    id=point_id(r["id"]),
                    vector={DENSE: d, SPARSE: s},
                    payload=payload(docs[r["doc_id"]], r, per_doc[r["doc_id"]]),
                )
                for r, d, s in zip(rows, dense, sparse)
            ]
            store.delete_docs(batch)  # a re-chunked doc may now have fewer chunks
            store.upsert(points)
            catalog.mark_indexed(batch)
            counts["indexed_docs"] += len(batch)
            counts["indexed_chunks"] += len(points)
            progress.advance(task, len(batch))

    counts["seconds"] = round(time.perf_counter() - t0)
    counts["collection_points"] = store.count()
    return counts
