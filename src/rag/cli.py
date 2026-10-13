import logging
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from rag.config import settings

app = typer.Typer(help="Enterprise RAG for forex, crypto and PSX market intelligence.", no_args_is_help=True)
console = Console()


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for noisy in ("trafilatura", "htmldate", "courlan"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)


@app.command()
def sources() -> None:
    """List configured data sources."""
    from rag.ingest.sources import build_connectors

    table = Table("name", "publisher", "type", "region", "markets", "relevance filter", "full text")
    for name, c in build_connectors().items():
        cfg = c.config
        table.add_row(name, cfg.publisher, cfg.doc_type.value, cfg.region,
                      ", ".join(m.value for m in cfg.markets) or "(tagged)",
                      "yes" if cfg.require_relevance else "", "yes" if cfg.fulltext else "")
    console.print(table)


@app.command()
def ingest(
    source: Annotated[list[str] | None, typer.Option("--source", "-s", help="Repeatable; default all")] = None,
    fulltext: Annotated[bool, typer.Option(help="Download article pages when feeds only carry summaries")] = True,
    limit: Annotated[int | None, typer.Option(help="Max items per source (for quick tests)")] = None,
) -> None:
    """Fetch new documents from sources into the catalog."""
    from rag.ingest.pipeline import run
    from rag.ingest.sources import build_connectors

    connectors = build_connectors()
    if source:
        unknown = set(source) - connectors.keys()
        if unknown:
            raise typer.BadParameter(f"unknown sources: {', '.join(sorted(unknown))}")
        connectors = {k: v for k, v in connectors.items() if k in source}

    results = run(connectors, fulltext=fulltext, limit=limit)
    cols = ["fetched", "new", "updated", "unchanged", "dropped", "fulltext_ok", "fulltext_failed", "errors"]
    table = Table("source", *cols, title="Ingest run")
    for name, counts in results.items():
        table.add_row(name, *(str(counts.get(c, 0)) for c in cols))
    console.print(table)


@app.command()
def stats() -> None:
    """Summarise what is in the catalog."""
    from rag.ingest.store import Catalog

    catalog = Catalog(settings.catalog_path)
    table = Table("source", "docs", "oldest", "newest", "avg chars", title=str(settings.catalog_path))
    total = 0
    for r in catalog.stats():
        total += r["docs"]
        table.add_row(r["source"], str(r["docs"]), r["oldest"][:16], r["newest"][:16], str(r["avg_chars"]))
    console.print(table)
    console.print("Docs per market: " + ", ".join(f"{r['market']}={r['docs']}" for r in catalog.market_stats()))
    console.print(f"Total documents: {total}")


@app.command()
def docs(
    market: Annotated[str | None, typer.Option("--market", "-m")] = None,
    source: Annotated[str | None, typer.Option("--source", "-s")] = None,
    query: Annotated[str | None, typer.Option("--query", "-q", help="Substring of title")] = None,
    limit: int = 30,
) -> None:
    """Browse documents in the catalog (newest first)."""
    from rag.ingest.store import Catalog

    table = Table("id", "published", "source", "markets", "chars", "chunks", "title")
    for r in Catalog(settings.catalog_path).list_documents(market, source, query, limit):
        status = r["n_chunks"] if r["n_chunks"] else (
            "dup" if r["duplicate_of"] else (r["skip_reason"] or "-")[:10])
        table.add_row(r["id"][:8], r["published_at"][:16], r["source"], r["markets"].strip("[]").replace('"', ""),
                      str(r["chars"]), str(status), r["title"][:70])
    console.print(table)


@app.command()
def show(
    doc_id: Annotated[str, typer.Argument(help="Document id or prefix (from `rag docs`)")],
    chunks: Annotated[bool, typer.Option(help="Also print the chunks")] = False,
) -> None:
    """Print one document (and optionally its chunks)."""
    from rag.ingest.store import Catalog

    catalog = Catalog(settings.catalog_path)
    doc = catalog.get_document(doc_id)
    if not doc:
        raise typer.BadParameter(f"no document {doc_id}")
    console.rule(doc.title)
    console.print(f"[bold]{doc.publisher}[/] | {doc.published_at:%Y-%m-%d %H:%M} UTC | {doc.url}")
    console.print(f"markets={[m.value for m in doc.markets]} instruments={doc.instruments} file={doc.file_path}")
    console.print(doc.text or "[dim](no text; see file)[/]")
    if chunks:
        for r in catalog.chunks_for([doc.id]):
            console.rule(f"chunk {r['idx']} | {r['n_tokens']} tokens | section={r['section']}")
            console.print(r["embed_text"])


@app.command()
def process() -> None:
    """Phase 2: parse, clean, dedupe and chunk new or changed documents."""
    from rag.processing.pipeline import run

    counts = run()
    console.print(dict(counts) or "Nothing to process.")


@app.command()
def index(rebuild: Annotated[bool, typer.Option(help="Drop and rebuild the collection")] = False) -> None:
    """Phase 3: embed chunks and sync them into Qdrant."""
    from rag.index.pipeline import run

    console.print(dict(run(rebuild=rebuild)))


@app.command()
def search(
    query: str,
    mode: Annotated[str, typer.Option(help="dense | bm25 | hybrid")] = "hybrid",
    market: Annotated[list[str] | None, typer.Option("--market", "-m")] = None,
    instrument: Annotated[list[str] | None, typer.Option("--instrument", "-i")] = None,
    days: Annotated[int | None, typer.Option(help="Only documents from the last N days")] = None,
    limit: int = 8,
) -> None:
    """Search the index (retrieval only; answers come in Phase 5)."""
    import time
    from datetime import UTC, datetime, timedelta

    from rag.index.embedder import get_embedder
    from rag.index.vector_store import SearchFilters, VectorStore

    filters = SearchFilters(
        markets=market or [], instruments=instrument or [],
        since=datetime.now(UTC) - timedelta(days=days) if days else None,
    )
    embedder = get_embedder()
    t0 = time.perf_counter()
    hits = VectorStore().search(query, embedder, mode=mode, filters=filters, limit=limit)
    ms = (time.perf_counter() - t0) * 1000
    table = Table("#", "score", "date", "publisher", "title / snippet", title=f"{mode} | {ms:.0f} ms")
    for i, h in enumerate(hits, 1):
        p = h.payload
        snippet = " ".join(h.text.split())[:160]
        table.add_row(str(i), f"{h.score:.3f}", p["published_at"][:10], p["publisher"][:16],
                      f"[bold]{p['title'][:80]}[/]\n[dim]{snippet}[/]")
    console.print(table)


@app.command()
def status() -> None:
    """Pipeline status across all phases."""
    from rag.index.vector_store import VectorStore
    from rag.ingest.store import Catalog

    s = Catalog(settings.catalog_path).pipeline_stats()
    for k in s.keys():  # noqa: SIM118 - iterating a sqlite3.Row yields values, not keys
        console.print(f"{k:>18}: {s[k]}")
    console.print(f"{'qdrant_points':>18}: {VectorStore().count()} ({settings.qdrant_mode} mode)")


if __name__ == "__main__":
    app()
