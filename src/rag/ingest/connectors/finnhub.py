from collections.abc import Iterable
from datetime import UTC, datetime

from rag.config import settings
from rag.ingest.connectors.base import SourceConfig, canonical_url, doc_id
from rag.ingest.http import Fetcher
from rag.ingest.models import RawDocument

API = "https://finnhub.io/api/v1/news"


class FinnhubNewsConnector:
    """Finnhub market news; each category returns the latest ~100 headlines with summaries."""

    def __init__(self, config: SourceConfig, category: str):
        self.config = config
        self.category = category

    def fetch(self, fetcher: Fetcher) -> Iterable[RawDocument]:
        if not settings.finnhub_api_key:
            raise RuntimeError("FINNHUB_API_KEY is not set")
        items = fetcher.get(
            API, params={"category": self.category, "token": settings.finnhub_api_key}, check_robots=False
        ).json()
        now = datetime.now(UTC)
        for it in items:
            if not it.get("url") or not it.get("headline"):
                continue
            yield RawDocument(
                id=doc_id(canonical_url(it["url"])),
                source=self.config.name,
                publisher=it.get("source") or self.config.publisher,
                doc_type=self.config.doc_type,
                url=it["url"],
                title=it["headline"].strip(),
                summary=(it.get("summary") or "").strip(),
                published_at=datetime.fromtimestamp(it["datetime"], tz=UTC),
                fetched_at=now,
                region=self.config.region,
                markets=list(self.config.markets),
                instruments=[s for s in (it.get("related") or "").split(",") if s],
                extra={"finnhub_id": it.get("id"), "category": it.get("category")},
            )
