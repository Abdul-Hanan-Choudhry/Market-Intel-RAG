import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rag.ingest.http import Fetcher
from rag.ingest.models import DocType, Market, RawDocument

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "cmpid", "taid")


def canonical_url(url: str) -> str:
    """Normalise a URL so the same article reached via different links gets one ID."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING_PREFIXES)]
    path = parts.path.replace("//", "/").rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, urlencode(query), ""))


def doc_id(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    publisher: str
    doc_type: DocType = DocType.NEWS
    region: str = "global"
    markets: tuple[Market, ...] = ()
    require_relevance: bool = False
    fulltext: bool = True
    extra: dict = field(default_factory=dict)


class Connector(Protocol):
    config: SourceConfig

    def fetch(self, fetcher: Fetcher) -> Iterable[RawDocument]: ...
