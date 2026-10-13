"""Near-duplicate detection with MinHash.

Wire stories (Reuters, APP) are syndicated by several outlets with small edits.
Exact URL dedup can't catch them, so we compare the *content*:

  1. Shingle each document into overlapping 5-word sequences.
  2. Jaccard(A, B) = |A ∩ B| / |A ∪ B| measures overlap, but comparing full sets is costly.
  3. MinHash compresses each set to NUM_PERM integers so that the fraction of equal
     positions between two signatures estimates their Jaccard similarity.

Signatures are stored in SQLite, so each new document is compared without re-reading old ones.
"""

import hashlib
import re
from datetime import datetime, timedelta

import numpy as np

NUM_PERM = 128
SHINGLE = 5
THRESHOLD = 0.7
WINDOW = timedelta(days=4)

_PRIME = np.uint64((1 << 61) - 1)
_rng = np.random.default_rng(42)
_A = _rng.integers(1, 1 << 31, NUM_PERM, dtype=np.uint64)
_B = _rng.integers(0, 1 << 32, NUM_PERM, dtype=np.uint64)
_WORD = re.compile(r"\w+")


def shingles(text: str) -> set[str]:
    words = _WORD.findall(text.lower())
    if len(words) < SHINGLE:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def minhash(text: str) -> np.ndarray:
    sh = shingles(text)
    if not sh:
        return np.full(NUM_PERM, np.iinfo(np.uint64).max, dtype=np.uint64)
    hashes = np.fromiter(
        (int.from_bytes(hashlib.blake2b(s.encode(), digest_size=4).digest(), "little") for s in sh),
        dtype=np.uint64,
        count=len(sh),
    )
    # (a*x + b) mod p for every (permutation, shingle) pair; values stay below 2^64.
    return ((np.outer(_A, hashes) + _B[:, None]) % _PRIME).min(axis=1)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(a == b))


def find_duplicate(sig: np.ndarray, published_at: datetime,
                   candidates: list[tuple[str, np.ndarray, datetime]]) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for doc_id, other, ts in candidates:
        if abs(ts - published_at) > WINDOW:
            continue
        s = similarity(sig, other)
        if s >= THRESHOLD and (best is None or s > best[1]):
            best = (doc_id, s)
    return best
