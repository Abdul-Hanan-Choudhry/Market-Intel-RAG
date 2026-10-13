from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Market(StrEnum):
    FOREX = "forex"
    CRYPTO = "crypto"
    PSX = "psx"
    MACRO = "macro"


class DocType(StrEnum):
    NEWS = "news"
    CENTRAL_BANK = "central_bank"
    FILING = "filing"


class RawDocument(BaseModel):
    """One source document exactly as acquired, before parsing/chunking (Phase 2)."""

    id: str
    source: str
    publisher: str
    doc_type: DocType
    url: str
    title: str
    summary: str = ""
    content: str = ""
    content_type: str = "text/plain"
    file_path: str | None = None
    published_at: datetime
    fetched_at: datetime
    date_inferred: bool = False
    region: str = "global"
    markets: list[Market] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content or self.summary

    @property
    def needs_fulltext(self) -> bool:
        return self.file_path is None and len(self.text) < 800
