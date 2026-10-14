"""HTTP API around the RAG pipeline (Phase 6).

    GET  /health       is the service up, which model is loaded
    GET  /stats        corpus size and freshness
    POST /search       retrieval only (debugging, "show me the evidence")
    POST /ask          full answer as one JSON response
    POST /ask/stream   the same answer as Server-Sent Events, token by token

Only this process opens the Qdrant store and loads the models, so the UI (and any other
client) just speaks HTTP. That is also how it would run in production: one model server,
many thin clients.

Run: rag serve   (or: uvicorn rag.api.app:app)
"""

import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag.config import settings
from rag.generation.answer import Answerer
from rag.index.vector_store import SearchFilters

log = logging.getLogger(__name__)


class Query(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    k: int = Field(default=settings.answer_k, ge=1, le=10)
    markets: list[str] = Field(default_factory=list, description="forex | crypto | psx | macro")
    days: int | None = Field(default=None, ge=1, le=365, description="Only documents from the last N days")

    def filters(self) -> SearchFilters | None:
        if not (self.markets or self.days):
            return None
        since = datetime.now(UTC) - timedelta(days=self.days) if self.days else None
        return SearchFilters(markets=self.markets, since=since)


def create_app(answerer: Answerer | None = None, catalog=None, warmup: bool = True) -> FastAPI:
    """Factory so tests can inject fakes instead of real models."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from rag.ingest.store import Catalog

        app.state.answerer = answerer or Answerer()
        app.state.catalog = catalog or Catalog(settings.catalog_path)
        if warmup:  # pay model loading at startup, not on the first user's question
            t = time.perf_counter()
            a = app.state.answerer
            a.retriever.retrieve("warm up", k=1)
            log.info("LLM ready: %s", a.llm.name)
            log.info("warm-up done in %.1fs", time.perf_counter() - t)
        yield

    app = FastAPI(title="Enterprise RAG - market intelligence", version="0.1.0", lifespan=lifespan)
    # The local Qdrant store and ONNX sessions are not meant for concurrent writers/readers
    # from many threads; one retrieval at a time costs ~2 s and keeps things safe.
    retrieval_lock = threading.Lock()

    def _answerer(request: Request) -> Answerer:
        return request.app.state.answerer

    @app.get("/health")
    def health(request: Request) -> dict:
        a = _answerer(request)
        return {"status": "ok", "llm": a.llm_name or "not loaded",
                "backend": settings.llm_backend, "qdrant_mode": settings.qdrant_mode}

    @app.get("/stats")
    def stats(request: Request) -> dict:
        cat = request.app.state.catalog
        per_source = [dict(r) for r in cat.stats()]
        return {
            "pipeline": dict(cat.pipeline_stats()),
            "markets": {r["market"]: r["docs"] for r in cat.market_stats()},
            "newest_document": max((r["newest"] for r in per_source), default=None),
            "sources": len(per_source),
        }

    @app.post("/search")
    def search(q: Query, request: Request) -> dict:
        with retrieval_lock:
            result = _answerer(request).retriever.retrieve(q.question, k=q.k, extra_filters=q.filters())
        return {"plan": result.plan.describe(), "timings_ms": result.timings_ms,
                "n_candidates": result.n_candidates, "chunks": [c.to_dict() for c in result.chunks]}

    def _events(q: Query, request: Request) -> Iterator[dict]:
        stream = _answerer(request).stream(q.question, k=q.k, filters=q.filters())
        with retrieval_lock:  # held only until the sources are ready
            first = next(stream)
        yield first
        yield from stream  # LocalLlama has its own lock for generation

    @app.post("/ask")
    def ask(q: Query, request: Request) -> dict:
        for event in _events(q, request):
            if event["type"] == "done":
                return event["answer"]
        raise RuntimeError("answer stream ended without a result")

    @app.post("/ask/stream")
    def ask_stream(q: Query, request: Request) -> StreamingResponse:
        def sse() -> Iterator[str]:
            try:
                for event in _events(q, request):
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            except Exception as exc:  # the HTTP status is already sent; report in-band
                log.exception("ask/stream failed")
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        # Starlette runs this sync generator in a worker thread, so CPU-bound
        # generation does not block other requests (like /health).
        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()
