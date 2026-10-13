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

-- Phase 2/3 pipeline state. A stage is stale when its stored hash differs from documents.content_hash.
CREATE TABLE IF NOT EXISTS doc_state (
    doc_id          TEXT PRIMARY KEY,
    processed_hash  TEXT,
    skip_reason     TEXT,
    duplicate_of    TEXT,
    minhash         BLOB,
    n_chunks        INTEGER NOT NULL DEFAULT 0,
    indexed_hash    TEXT,
    indexed_at      TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    section     TEXT,
    text        TEXT NOT NULL,
    embed_text  TEXT NOT NULL,
    n_tokens    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);

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

    def get_document(self, doc_id: str) -> RawDocument | None:
        row = self.conn.execute(
            "SELECT data FROM documents WHERE id = ? OR id LIKE ?", (doc_id, f"{doc_id}%")
        ).fetchone()
        return RawDocument.model_validate_json(row["data"]) if row else None

    def list_documents(self, market: str | None = None, source: str | None = None,
                       query: str | None = None, limit: int = 30) -> list[sqlite3.Row]:
        sql = """SELECT d.id, d.source, d.published_at, d.title, d.markets,
                        LENGTH(json_extract(d.data, '$.content')) + LENGTH(json_extract(d.data, '$.summary')) AS chars,
                        s.n_chunks, s.skip_reason, s.duplicate_of
                 FROM documents d LEFT JOIN doc_state s ON s.doc_id = d.id WHERE 1=1"""
        args: list = []
        if market:
            sql += " AND EXISTS (SELECT 1 FROM json_each(d.markets) WHERE value = ?)"
            args.append(market)
        if source:
            sql += " AND d.source = ?"
            args.append(source)
        if query:
            sql += " AND d.title LIKE ?"
            args.append(f"%{query}%")
        sql += " ORDER BY d.published_at DESC LIMIT ?"
        return self.conn.execute(sql, (*args, limit)).fetchall()

    def pending_processing(self, version: str) -> list[tuple[RawDocument, str]]:
        """Docs whose content or processing config changed. Returns (doc, fingerprint to store)."""
        rows = self.conn.execute(
            """SELECT d.data, d.content_hash || ':' || ? AS fp FROM documents d
               LEFT JOIN doc_state s ON s.doc_id = d.id
               WHERE s.processed_hash IS NULL OR s.processed_hash != d.content_hash || ':' || ?
               ORDER BY d.published_at""",
            (version, version),
        ).fetchall()
        return [(RawDocument.model_validate_json(r["data"]), r["fp"]) for r in rows]

    def minhash_candidates(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT s.doc_id, s.minhash, d.published_at FROM doc_state s JOIN documents d ON d.id = s.doc_id
               WHERE s.minhash IS NOT NULL AND s.duplicate_of IS NULL AND s.skip_reason IS NULL"""
        ).fetchall()

    def save_processed(self, doc_id: str, processed_hash: str, chunks: list[dict],
                       skip_reason: str | None = None, duplicate_of: str | None = None,
                       minhash: bytes | None = None) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            c.executemany(
                """INSERT INTO chunks (id, doc_id, idx, section, text, embed_text, n_tokens)
                   VALUES (:id, :doc_id, :idx, :section, :text, :embed_text, :n_tokens)""",
                chunks,
            )
            c.execute(
                """INSERT INTO doc_state (doc_id, processed_hash, skip_reason, duplicate_of, minhash, n_chunks)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(doc_id) DO UPDATE SET processed_hash=excluded.processed_hash,
                     skip_reason=excluded.skip_reason, duplicate_of=excluded.duplicate_of,
                     minhash=excluded.minhash, n_chunks=excluded.n_chunks""",
                (doc_id, processed_hash, skip_reason, duplicate_of, minhash, len(chunks)),
            )

    def mark_superseded(self, old_id: str, new_id: str) -> None:
        """An updated version of a story replaces the older one; its chunks leave the index."""
        with self.transaction() as c:
            c.execute("DELETE FROM chunks WHERE doc_id = ?", (old_id,))
            c.execute("UPDATE doc_state SET duplicate_of = ?, n_chunks = 0 WHERE doc_id = ?", (new_id, old_id))

    def pending_indexing(self) -> tuple[list[str], list[str]]:
        """Returns (doc_ids to (re)index, doc_ids whose points must be removed)."""
        to_index = [r[0] for r in self.conn.execute(
            """SELECT doc_id FROM doc_state WHERE processed_hash IS NOT NULL AND n_chunks > 0
               AND (indexed_hash IS NULL OR indexed_hash != processed_hash)"""
        )]
        to_remove = [r[0] for r in self.conn.execute(
            "SELECT doc_id FROM doc_state WHERE n_chunks = 0 AND indexed_hash IS NOT NULL"
        )]
        return to_index, to_remove

    def chunks_for(self, doc_ids: list[str]) -> list[sqlite3.Row]:
        marks = ",".join("?" * len(doc_ids))
        return self.conn.execute(
            f"SELECT * FROM chunks WHERE doc_id IN ({marks}) ORDER BY doc_id, idx", doc_ids
        ).fetchall()

    def mark_indexed(self, doc_ids: list[str], removed: bool = False) -> None:
        now = datetime.now(UTC).isoformat()
        with self.transaction() as c:
            c.executemany(
                "UPDATE doc_state SET indexed_hash = ?, indexed_at = ? WHERE doc_id = ?"
                if removed else
                "UPDATE doc_state SET indexed_hash = processed_hash, indexed_at = ? WHERE doc_id = ?",
                [((None, now, d) if removed else (now, d)) for d in doc_ids],
            )

    def reset_index_state(self) -> None:
        with self.transaction() as c:
            c.execute("UPDATE doc_state SET indexed_hash = NULL, indexed_at = NULL")

    def pipeline_stats(self) -> sqlite3.Row:
        return self.conn.execute(
            """SELECT (SELECT COUNT(*) FROM documents) AS documents,
                      (SELECT COUNT(*) FROM doc_state WHERE processed_hash IS NOT NULL) AS processed,
                      (SELECT COUNT(*) FROM doc_state WHERE duplicate_of IS NOT NULL) AS duplicates,
                      (SELECT COUNT(*) FROM doc_state WHERE skip_reason IS NOT NULL) AS skipped,
                      (SELECT COUNT(*) FROM chunks) AS chunks,
                      (SELECT CAST(AVG(n_tokens) AS INT) FROM chunks) AS avg_chunk_tokens,
                      (SELECT COUNT(*) FROM doc_state WHERE indexed_hash IS NOT NULL) AS indexed_docs"""
        ).fetchone()

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
