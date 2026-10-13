"""Drop-folder connector for documents you download by hand.

Layout: data/inbox/<PUBLISHER>/<file>.pdf|html|txt|md, e.g. data/inbox/SBP/MPS_2026-09.pdf.
Use it for sources that block automation (SBP monetary policy statements, PSX notices,
broker research PDFs). Text extraction happens in Phase 2.
"""

import hashlib
import mimetypes
from collections.abc import Iterable
from datetime import UTC, datetime

from rag.config import settings
from rag.ingest.connectors.base import SourceConfig
from rag.ingest.http import Fetcher
from rag.ingest.models import DocType, Market, RawDocument

SUPPORTED = {".pdf", ".html", ".htm", ".txt", ".md"}

KNOWN_PUBLISHERS: dict[str, tuple[DocType, str, tuple[Market, ...]]] = {
    "SBP": (DocType.CENTRAL_BANK, "pk", (Market.MACRO, Market.FOREX, Market.PSX)),
    "PSX": (DocType.FILING, "pk", (Market.PSX,)),
    "SECP": (DocType.FILING, "pk", (Market.PSX,)),
    "FED": (DocType.CENTRAL_BANK, "us", (Market.MACRO, Market.FOREX)),
    "ECB": (DocType.CENTRAL_BANK, "eu", (Market.MACRO, Market.FOREX)),
}


class InboxConnector:
    def __init__(self, config: SourceConfig):
        self.config = config

    def fetch(self, fetcher: Fetcher) -> Iterable[RawDocument]:
        root = settings.inbox_dir
        root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in SUPPORTED or not path.is_file():
                continue
            publisher = path.parent.name if path.parent != root else "manual"
            doc_type, region, markets = KNOWN_PUBLISHERS.get(publisher.upper(), (DocType.FILING, "global", ()))
            digest = hashlib.sha1(path.read_bytes()).hexdigest()
            yield RawDocument(
                id=digest[:16],
                source=self.config.name,
                publisher=publisher,
                doc_type=doc_type,
                url=path.resolve().as_uri(),
                title=path.stem.replace("_", " "),
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                file_path=str(path.relative_to(settings.data_dir)),
                published_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                fetched_at=now,
                date_inferred=True,
                region=region,
                markets=list(markets),
            )
