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
def retrieve(question: str, k: int = 5) -> None:
    """Phase 4: run the full retrieval pipeline and show every scoring signal."""
    from rag.retrieval.retriever import Retriever

    result = Retriever().retrieve(question, k=k)
    console.print(f"[bold]Plan:[/] {result.plan.describe()}")
    t = result.timings_ms
    table = Table("#", "relevance", "recency", "boost", "score", "date", "publisher", "title / snippet",
                  title=f"{result.n_candidates} candidates | search {t['search']:.0f} ms | rerank {t['rerank']:.0f} ms")
    for i, c in enumerate(result.chunks, 1):
        p = c.payload
        table.add_row(str(i), f"{c.relevance:.3f}", f"{c.recency:.2f}", f"{c.boost:.2f}", f"{c.score:.3f}",
                      p["published_at"][:10], p["publisher"][:14],
                      f"[bold]{p['title'][:70]}[/]\n[dim]{' '.join(c.hit.text.split())[:140]}[/]")
    console.print(table)


@app.command("eval-retrieval")
def eval_retrieval(
    config: Annotated[list[str] | None, typer.Option("--config", "-c")] = None,
    details: Annotated[bool, typer.Option(help="Show rank of the first relevant doc per question")] = False,
) -> None:
    """Phase 4: score retrieval configurations on the labelled question set."""
    from rag.retrieval.evaluate import CONFIGS, evaluate
    from rag.retrieval.retriever import Retriever

    configs = {k: v for k, v in CONFIGS.items() if not config or k in config}
    rows = evaluate(Retriever(), configs)
    table = Table("config", "Hit@1", "Hit@5", "MRR", "ms/query", title="Retrieval quality (20 questions)")
    for r in rows:
        table.add_row(r.config, f"{r.hit1:.0%}", f"{r.hit5:.0%}", f"{r.mrr:.3f}", f"{r.ms_per_query:.0f}")
    console.print(table)
    for r in rows:
        if r.misses:
            console.print(f"[yellow]{r.config}[/] missed top-5: " + " | ".join(m[:50] for m in r.misses))
    if details:
        detail = Table("question", *[r.config for r in rows], title="Rank of first relevant document")
        for q in rows[0].ranks:
            detail.add_row(q[:60], *[str(r.ranks[q] or "-") for r in rows])
        console.print(detail)


@app.command("calibrate-refusal")
def calibrate_refusal() -> None:
    """Phase 5: compare reranker relevance for answerable vs off-topic questions."""
    from rag.retrieval.evaluate import OFF_TOPIC, load_questions
    from rag.retrieval.retriever import Retriever

    retriever = Retriever()
    groups = {"on-topic": [q["question"] for q in load_questions()], "off-topic": OFF_TOPIC}
    table = Table("group", "question", "best relevance", "refused?", title=f"refuse_below = {settings.refuse_below}")
    for group, questions in groups.items():
        for q in questions:
            best = retriever.retrieve(q, k=settings.answer_k).best_relevance
            table.add_row(group, q[:70], f"{best:.4f}", "yes" if best < settings.refuse_below else "")
    console.print(table)


@app.command()
def ask(
    question: str,
    k: Annotated[int, typer.Option(help="Chunks to retrieve")] = settings.answer_k,
    market: Annotated[list[str] | None, typer.Option("--market", "-m")] = None,
    show_prompt: Annotated[bool, typer.Option(help="Print the exact source text the LLM sees")] = False,
) -> None:
    """Phase 5: answer a question from the indexed documents, with citations."""
    from rag.generation.answer import Answerer
    from rag.index.vector_store import SearchFilters

    filters = SearchFilters(markets=market) if market else None
    console.print("[dim]retrieving...[/]")
    for event in Answerer().stream(question, k=k, filters=filters):
        if event["type"] == "retrieval":
            console.print(f"[bold]Plan:[/] {event['plan']['description']}")
            for s in event["sources"]:
                console.print(f"  [cyan][{s['n']}][/] {s['title'][:80]} [dim]({s['publisher']}, "
                              f"{s['published_at']}, relevance {s['relevance']:.2f})[/]")
                if show_prompt:
                    console.print(f"[dim]{s['text']}[/]")
            if event["sources"]:
                console.print("[dim]generating (the first word takes longest on CPU)...[/]\n")
        elif event["type"] == "token":
            console.print(event["text"], end="", highlight=False, markup=False)
        elif event["type"] == "error":
            console.print(f"\n[red]error:[/] {event['message']}")
            if event.get("partial_answer"):
                console.print(f"[dim]partial output before the stall: {event['partial_answer']!r}[/]")
        else:
            a = event["answer"]
            if not a["generation"]:  # refused before generation
                console.print(f"[yellow]{a['answer']}[/]\n[dim]{a['refusal_reason']}[/]")
            t, g = a["timings_ms"], a["generation"]
            console.print()
            for w in a["warnings"]:
                console.print(f"[yellow]warning:[/] {w}")
            for s in a["sources"]:
                if s["n"] in a["cited"]:
                    console.print(f"[cyan][{s['n']}][/] {s['url']}")
            timing = f"retrieval {t.get('retrieval_search', 0) + t.get('retrieval_rerank', 0):.0f} ms"
            if g:
                timing += (f" | first token {g['time_to_first_token_ms'] / 1000:.1f} s | "
                           f"{g['completion_tokens']} tokens at {g['tokens_per_second']} tok/s | "
                           f"prompt ~{g['prompt_tokens']} tokens | {a['model']}")
            console.print(f"[dim]{timing} | total {t['total'] / 1000:.1f} s[/]")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Phase 6: start the HTTP API (models load once, at startup)."""
    import uvicorn

    # One worker: each worker would load its own copy of the LLM and lock the local Qdrant store.
    uvicorn.run("rag.api.app:app", host=host, port=port, workers=1, log_level="info")


@app.command()
def ui(port: int = 8501) -> None:
    """Phase 6: start the Streamlit chat UI (needs `rag serve` running)."""
    import subprocess
    import sys

    from rag.config import ROOT

    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "ui" / "app.py"),
                    "--server.port", str(port), "--browser.gatherUsageStats", "false"], check=False)


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
