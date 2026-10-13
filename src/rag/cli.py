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


if __name__ == "__main__":
    app()
