import calendar
import html
from collections.abc import Iterable
from datetime import UTC, datetime

import feedparser
from bs4 import BeautifulSoup

from rag.ingest.connectors.base import SourceConfig, canonical_url, doc_id
from rag.ingest.http import Fetcher
from rag.ingest.models import RawDocument


def html_to_text(markup: str) -> str:
    if "<" not in markup:
        return html.unescape(markup).strip()
    return BeautifulSoup(markup, "lxml").get_text(" ", strip=True)


def entry_datetime(entry: dict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if entry.get(key):
            return datetime.fromtimestamp(calendar.timegm(entry[key]), tz=UTC)
    return None


class RSSConnector:
    def __init__(self, config: SourceConfig, url: str):
        self.config = config
        self.url = url

    def fetch(self, fetcher: Fetcher) -> Iterable[RawDocument]:
        feed = feedparser.parse(fetcher.get(self.url).content)
        if not feed.entries and not feed.version:
            raise ValueError(f"not a valid feed (got non-RSS/Atom content) at {self.url}")
        now = datetime.now(UTC)
        for e in feed.entries:
            link = e.get("link")
            if not link or not e.get("title"):
                continue
            body = (e.get("content") or [{}])[0].get("value", "")
            summary = html_to_text(e.get("summary", ""))
            content = html_to_text(body) if body else ""
            if content == summary:
                summary = ""
            published = entry_datetime(e)
            yield RawDocument(
                id=doc_id(canonical_url(link)),
                source=self.config.name,
                publisher=self.config.publisher,
                doc_type=self.config.doc_type,
                url=link,
                title=html_to_text(e.title),
                summary=summary,
                content=content,
                published_at=published or now,
                fetched_at=now,
                date_inferred=published is None,
                region=self.config.region,
                markets=list(self.config.markets),
                extra={"authors": [a.get("name") for a in e.get("authors", []) if a.get("name")],
                       "categories": [t.get("term") for t in e.get("tags", []) if t.get("term")]},
            )
