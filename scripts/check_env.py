"""Phase 0 smoke test: verifies hardware, imports and that each layer of the stack runs on this machine."""

import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console
from rich.table import Table

from rag.config import settings

console = Console()
results: list[tuple[str, bool, str]] = []


def check(name):
    def wrap(fn):
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.perf_counter() - t0:.1f}s)"))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn

    return wrap


@check("Python")
def _():
    assert sys.version_info[:2] == (3, 12)
    return f"{platform.python_version()} on {platform.system()}"


@check("CPU / RAM")
def _():
    import psutil

    return f"{os.cpu_count()} threads, {psutil.virtual_memory().total / 2**30:.1f} GB RAM"


@check("llama.cpp (GGUF runtime)")
def _():
    import llama_cpp

    info = llama_cpp.llama_print_system_info().decode()
    flags = [f for f in ("AVX2", "AVX512", "FMA", "F16C") if f"{f} = 1" in info]
    return f"v{llama_cpp.__version__}, CPU features: {', '.join(flags) or 'none detected'}"


@check("Dense embeddings (fastembed)")
def _():
    from fastembed import TextEmbedding

    model = TextEmbedding(settings.embed_model, cache_dir=str(settings.fastembed_cache))
    vec = next(iter(model.embed(["Fed holds rates steady"])))
    return f"{settings.embed_model} -> dim {len(vec)}"


@check("Sparse BM25 (fastembed)")
def _():
    from fastembed import SparseTextEmbedding

    model = SparseTextEmbedding(settings.sparse_model, cache_dir=str(settings.fastembed_cache))
    sv = next(iter(model.embed(["Fed holds rates steady"])))
    return f"{settings.sparse_model} -> {len(sv.indices)} non-zero terms"


@check("Reranker (cross-encoder)")
def _():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    model = TextCrossEncoder(settings.rerank_model, cache_dir=str(settings.fastembed_cache))
    scores = list(
        model.rerank(
            "What did the Fed decide?",
            ["The FOMC kept the policy rate unchanged.", "Apple released a new iPhone."],
        )
    )
    assert scores[0] > scores[1], scores
    return f"relevant={scores[0]:.2f} > irrelevant={scores[1]:.2f}"


@check("Qdrant hybrid query (in-memory)")
def _():
    from fastembed import SparseTextEmbedding, TextEmbedding
    from qdrant_client import QdrantClient, models

    dense = TextEmbedding(settings.embed_model, cache_dir=str(settings.fastembed_cache))
    sparse = SparseTextEmbedding(settings.sparse_model, cache_dir=str(settings.fastembed_cache))

    def sparse_vec(text: str, query: bool = False) -> models.SparseVector:
        sv = next(iter(sparse.query_embed(text) if query else sparse.embed([text])))
        return models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())

    client = QdrantClient(":memory:")
    docs = [
        "The FOMC kept the federal funds rate at 4.25-4.50 percent.",
        "Brent crude rose 3% after OPEC+ announced output cuts.",
        "NVIDIA reported record data center revenue.",
    ]
    client.create_collection(
        "smoke",
        vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    client.upsert(
        "smoke",
        points=[
            models.PointStruct(
                id=i,
                vector={"dense": vec.tolist(), "bm25": sparse_vec(d)},
                payload={"text": d},
            )
            for i, (d, vec) in enumerate(zip(docs, dense.embed(docs)))
        ],
    )
    q = "oil prices OPEC"
    hits = client.query_points(
        "smoke",
        prefetch=[
            models.Prefetch(query=next(iter(dense.query_embed(q))).tolist(), using="dense", limit=3),
            models.Prefetch(query=sparse_vec(q, query=True), using="bm25", limit=3),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=1,
    ).points
    assert "OPEC" in hits[0].payload["text"]
    return f"top hit for '{q}': {hits[0].payload['text'][:45]}..."


@check("Disk space (project drive)")
def _():
    import shutil

    free = shutil.disk_usage(Path(__file__).anchor).free / 2**30
    return f"{free:.0f} GB free"


table = Table(title="Enterprise-RAG environment check")
table.add_column("Component")
table.add_column("Status")
table.add_column("Detail")
for name, ok, detail in results:
    table.add_row(name, "[green]OK[/]" if ok else "[red]FAIL[/]", detail)
console.print(table)
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
