"""Phase 2 pipeline: parse -> clean -> filter -> dedupe -> chunk, incrementally."""

import logging
from collections import Counter
from datetime import datetime

import numpy as np

from rag.config import settings
from rag.ingest.store import Catalog
from rag.processing import dedup
from rag.processing.chunk import (
    MAX_TOKENS,
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    chunk_text,
    contextual_header,
    count_tokens,
)
from rag.processing.clean import clean_text
from rag.processing.parse import extract_text

log = logging.getLogger(__name__)

MIN_TOKENS = 25  # title + body; a headline plus one sentence is still a usable news fact

# Part of every processed fingerprint: changing any of these re-processes and re-indexes everything.
VERSION = f"p1-t{TARGET_TOKENS}-m{MAX_TOKENS}-o{OVERLAP_TOKENS}-min{MIN_TOKENS}-d{dedup.THRESHOLD}"


def run(catalog: Catalog | None = None) -> Counter:
    catalog = catalog or Catalog(settings.catalog_path)
    counts: Counter = Counter()
    candidates: list[tuple[str, np.ndarray, datetime]] = [
        (r["doc_id"], np.frombuffer(r["minhash"], dtype=np.uint64), datetime.fromisoformat(r["published_at"]))
        for r in catalog.minhash_candidates()
    ]

    for doc, fingerprint in catalog.pending_processing(VERSION):
        counts["seen"] += 1
        try:
            text = clean_text(extract_text(doc), doc.title)
        except Exception as e:  # noqa: BLE001
            log.warning("parse failed for %s (%s): %s", doc.id, doc.title[:50], e)
            catalog.save_processed(doc.id, fingerprint, [], skip_reason=f"parse_error: {e}"[:200])
            counts["parse_error"] += 1
            continue

        if count_tokens(f"{doc.title}\n{text}") < MIN_TOKENS:
            catalog.save_processed(doc.id, fingerprint, [], skip_reason="too_short")
            counts["too_short"] += 1
            continue

        sig = dedup.minhash(text)
        candidates = [c for c in candidates if c[0] != doc.id]
        dup = dedup.find_duplicate(sig, doc.published_at, candidates)
        if dup:
            other_id = dup[0]
            other_ts = next(ts for cid, _, ts in candidates if cid == other_id)
            if doc.published_at < other_ts:
                log.debug("%s is an older version of %s (%.2f)", doc.id, *dup)
                catalog.save_processed(doc.id, fingerprint, [], duplicate_of=other_id, minhash=sig.tobytes())
                counts["duplicate"] += 1
                continue
            log.debug("%s supersedes %s (%.2f)", doc.id, *dup)
            catalog.mark_superseded(other_id, doc.id)
            candidates = [c for c in candidates if c[0] != other_id]
            counts["superseded"] += 1
        candidates.append((doc.id, sig, doc.published_at))

        rows = []
        for ch in chunk_text(text):
            header = contextual_header(doc, ch.section)
            rows.append({
                "id": f"{doc.id}:{ch.idx}",
                "doc_id": doc.id,
                "idx": ch.idx,
                "section": ch.section,
                "text": ch.text,
                "embed_text": f"{header}\n{ch.text}",
                "n_tokens": ch.n_tokens,
            })
        catalog.save_processed(doc.id, fingerprint, rows, minhash=sig.tobytes())
        counts["chunked_docs"] += 1
        counts["chunks"] += len(rows)
    return counts
