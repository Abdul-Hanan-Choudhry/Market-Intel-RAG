"""SQLite document catalog: the system of record for everything ingested.

Each row keeps the full RawDocument JSON plus a content hash, so later phases can
tell new / changed / unchanged documents apart and only re-index what changed.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from rag.ingest.models import RawDocument

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    publisher     TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    markets       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_documents_published ON documents(published_at);
CREATE INDEX IF NOT EXISTS ix_documents_source ON documents(source);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    fetched     INTEGER NOT NULL,
    new         INTEGER NOT NULL,
    updated     INTEGER NOT NULL,
    unchanged   INTEGER NOT NULL,
    dropped     INTEGER NOT NULL,
    errors      INTEGER NOT NULL
);
"""

UpsertResult = Literal["new", "updated", "unchanged"]


def content_hash(doc: RawDocument) -> str:
    return hashlib.sha256(f"{doc.title}\n{doc.text}\n{doc.file_path}".encode()).hexdigest()


class Catalog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    def exists(self, doc_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone() is not None

    def upsert(self, doc: RawDocument) -> UpsertResult:
        h = content_hash(doc)
        row = self.conn.execute(
            "SELECT content_hash, version FROM documents WHERE id = ?", (doc.id,)
        ).fetchone()
        if row and row["content_hash"] == h:
            return "unchanged"
        values = (
            doc.source, doc.publisher, doc.doc_type.value, doc.url, doc.title,
            doc.published_at.isoformat(), doc.fetched_at.isoformat(),
            json.dumps([m.value for m in doc.markets]), h, doc.model_dump_json(),
        )
        with self.transaction() as c:
            if row:
                c.execute(
                    """UPDATE documents SET source=?, publisher=?, doc_type=?, url=?, title=?,
                       published_at=?, fetched_at=?, markets=?, content_hash=?, data=?,
                       version=version+1 WHERE id=?""",
                    (*values, doc.id),
                )
                return "updated"
            c.execute(
                """INSERT INTO documents (source, publisher, doc_type, url, title, published_at,
                   fetched_at, markets, content_hash, data, id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (*values, doc.id),
            )
            return "new"

    def log_run(self, source: str, started_at: datetime, counts: dict[str, int]) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO ingest_runs (source, started_at, finished_at, fetched, new, updated,
                   unchanged, dropped, errors) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    source, started_at.isoformat(), datetime.now(UTC).isoformat(),
                    *(counts.get(k, 0) for k in ("fetched", "new", "updated", "unchanged", "dropped", "errors")),
                ),
            )

    def iter_documents(self) -> Iterator[RawDocument]:
        for row in self.conn.execute("SELECT data FROM documents ORDER BY published_at"):
            yield RawDocument.model_validate_json(row["data"])

    def stats(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT source, COUNT(*) AS docs, MIN(published_at) AS oldest, MAX(published_at) AS newest,
                      CAST(AVG(LENGTH(json_extract(data, '$.content')) + LENGTH(json_extract(data, '$.summary'))) AS INT) AS avg_chars
               FROM documents GROUP BY source ORDER BY docs DESC"""
        ).fetchall()

    def market_stats(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT value AS market, COUNT(*) AS docs FROM documents, json_each(documents.markets)
               GROUP BY value ORDER BY docs DESC"""
        ).fetchall()
