"""Token-aware, structure-respecting chunking.

Design choices (each is a lever we will measure in Phase 7):
- Size is counted in *embedding-model tokens*, because bge-small truncates at 512.
- Chunks are packed from whole paragraphs; only oversized paragraphs get split by sentence.
- Consecutive chunks overlap by a sentence or two so a fact on a boundary isn't lost.
- Every chunk gets a contextual header (title, publisher, date, section) prepended for
  embedding, because a paragraph like "The committee held rates at 12%" means nothing
  without knowing it came from the SBP in September.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from tokenizers import Tokenizer

from rag.config import settings
from rag.ingest.models import RawDocument

TARGET_TOKENS = 350
MAX_TOKENS = 450
OVERLAP_TOKENS = 60

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


@lru_cache(maxsize=1)
def tokenizer() -> Tokenizer:
    tok = Tokenizer.from_pretrained(settings.embed_model)
    tok.no_truncation()
    return tok


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


@dataclass
class Chunk:
    idx: int
    text: str
    section: str | None
    n_tokens: int


def is_heading(line: str, next_line: str | None) -> bool:
    words = line.split()
    return (
        0 < len(words) <= 12
        and len(line) <= 90
        and not line.endswith((".", ",", ";", ":", "?", "!", '"', "”"))
        and next_line is not None
        and len(next_line) > 2 * len(line)
    )


def split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(paragraph) if s.strip()]


def _units(text: str) -> list[tuple[str, str | None, int]]:
    """Paragraph-level units (text, section, tokens); oversized paragraphs become sentences."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    units: list[tuple[str, str | None, int]] = []
    section = None
    for i, line in enumerate(lines):
        if is_heading(line, lines[i + 1] if i + 1 < len(lines) else None):
            section = line
            continue
        n = count_tokens(line)
        if n <= MAX_TOKENS:
            units.append((line, section, n))
            continue
        for sent in split_sentences(line):
            sn = count_tokens(sent)
            if sn <= MAX_TOKENS:
                units.append((sent, section, sn))
            else:  # pathological: a table row or run-on line; hard-split by tokens
                ids = tokenizer().encode(sent, add_special_tokens=False)
                for start in range(0, len(ids.ids), TARGET_TOKENS):
                    lo, hi = ids.offsets[start][0], ids.offsets[min(start + TARGET_TOKENS, len(ids.ids)) - 1][1]
                    units.append((sent[lo:hi], section, min(TARGET_TOKENS, len(ids.ids) - start)))
    return units


def _tail_overlap(parts: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Last sentences of the previous chunk, up to OVERLAP_TOKENS."""
    sentences = [s for text, _ in parts for s in split_sentences(text)]
    tail: list[tuple[str, int]] = []
    total = 0
    for s in reversed(sentences):
        n = count_tokens(s)
        if total + n > OVERLAP_TOKENS:
            break
        tail.insert(0, (s, n))
        total += n
    return tail


def chunk_text(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    parts: list[tuple[str, int]] = []
    size = 0
    section: str | None = None
    has_new = False

    def flush() -> None:
        nonlocal parts, size, has_new
        if parts and has_new:
            body = "\n".join(t for t, _ in parts)
            chunks.append(Chunk(len(chunks), body, section, count_tokens(body)))
        parts = _tail_overlap(parts) if parts else []
        size = sum(n for _, n in parts)
        has_new = False

    for unit, unit_section, n in _units(text):
        if unit_section != section and parts:
            flush()
            parts, size = [], 0  # no overlap across section boundaries
        section = unit_section
        if size + n > TARGET_TOKENS and has_new:
            flush()
        parts.append((unit, n))
        size += n
        has_new = True
    flush()
    return chunks


def contextual_header(doc: RawDocument, section: str | None) -> str:
    bits = [doc.title, f"{doc.publisher}, {doc.published_at:%d %b %Y}"]
    if section:
        bits.append(section)
    return " | ".join(bits)
