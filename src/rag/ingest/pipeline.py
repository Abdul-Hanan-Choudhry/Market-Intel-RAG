"""Ingestion pipeline: fetch -> dedupe -> enrich full text -> tag -> filter -> store."""

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import trafilatura

from rag.config import settings
from rag.ingest.connectors.base import Connector
from rag.ingest.http import Fetcher
from rag.ingest.models import RawDocument
from rag.ingest.store import Catalog
from rag.ingest.tagging import extract_instruments, tag_markets

log = logging.getLogger(__name__)


def enrich_fulltext(doc: RawDocument, fetcher: Fetcher) -> RawDocument:
    """Download the article page; keep extracted text if it beats the feed summary, save PDFs."""
    try:
        r = fetcher.get(doc.url)
    except Exception as e:  # noqa: BLE001
        log.debug("fulltext failed for %s: %s", doc.url, e)
        doc.extra["fulltext_error"] = f"{type(e).__name__}: {e}"[:200]
        return doc

    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or doc.url.lower().endswith(".pdf"):
        rel = f"raw/files/{doc.id}.pdf"
        path = settings.data_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return doc.model_copy(update={"file_path": rel, "content_type": "application/pdf"})

    text = trafilatura.extract(r.text, favor_precision=True, include_comments=False, include_tables=True)
    update: dict = {}
    if text and len(text) > len(doc.text):
        update["content"] = text
    if doc.date_inferred:
        meta = trafilatura.extract_metadata(r.text)
        if meta and meta.date:
            update["published_at"] = datetime.fromisoformat(meta.date).replace(tzinfo=UTC)
            update["date_inferred"] = False
    return doc.model_copy(update=update)


def tag(doc: RawDocument) -> tuple[RawDocument, bool]:
    """Returns the tagged document and whether its own text matched any market."""
    detected = tag_markets(doc.title, doc.text)
    markets = sorted(set(doc.markets) | detected)
    instruments = sorted(set(doc.instruments) | set(extract_instruments(f"{doc.title}\n{doc.text}")))
    return doc.model_copy(update={"markets": markets, "instruments": instruments}), bool(detected)


def run_source(connector: Connector, fetcher: Fetcher, catalog: Catalog, fulltext: bool,
               seen: set[str], limit: int | None = None) -> Counter:
    cfg = connector.config
    started = datetime.now(UTC)
    counts: Counter = Counter()
    try:
        docs = list(connector.fetch(fetcher))[:limit]
    except Exception as e:  # noqa: BLE001
        log.error("[%s] fetch failed: %s", cfg.name, e)
        counts["errors"] += 1
        catalog.log_run(cfg.name, started, counts)
        return counts

    counts["fetched"] = len(docs)
    fresh = []
    for d in docs:
        if d.id in seen or (cfg.name != "inbox" and catalog.exists(d.id)):
            counts["unchanged"] += 1
        else:
            fresh.append(d)
        seen.add(d.id)

    if cfg.require_relevance:
        # Cheap pre-filter on headline + summary so we don't download pages we will drop anyway.
        kept = [d for d in fresh if not d.needs_fulltext or tag_markets(d.title, d.text, min_body_hits=1)]
        counts["dropped"] += len(fresh) - len(kept)
        fresh = kept

    if fulltext and cfg.fulltext:
        needs = [d for d in fresh if d.needs_fulltext]
        with ThreadPoolExecutor(max_workers=6) as pool:
            enriched = dict(zip([d.id for d in needs], pool.map(lambda d: enrich_fulltext(d, fetcher), needs)))
        fresh = [enriched.get(d.id, d) for d in fresh]
        counts["fulltext_ok"] = sum(1 for d in enriched.values() if "fulltext_error" not in d.extra)
        counts["fulltext_failed"] = len(enriched) - counts["fulltext_ok"]

    for d in fresh:
        d, relevant = tag(d)
        if cfg.require_relevance and not relevant:
            counts["dropped"] += 1
            continue
        counts[catalog.upsert(d)] += 1

    catalog.log_run(cfg.name, started, counts)
    return counts


def run(connectors: dict[str, Connector], fulltext: bool = True, limit: int | None = None) -> dict[str, Counter]:
    catalog = Catalog(settings.catalog_path)
    fetcher = Fetcher()
    seen: set[str] = set()
    try:
        return {name: run_source(c, fetcher, catalog, fulltext, seen, limit) for name, c in connectors.items()}
    finally:
        fetcher.close()
