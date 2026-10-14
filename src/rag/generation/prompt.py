"""Turn retrieved chunks into the messages the LLM sees.

The system prompt never changes between requests. llama.cpp keeps the processed tokens of
the previous prompt, so an identical prefix is not re-read: on CPU that saves seconds.
Everything that changes (date, sources, question) goes in the user message.
"""

from dataclasses import dataclass, field
from datetime import datetime

from rag.generation.llm import Message
from rag.retrieval.retriever import RetrievedChunk

REFUSAL = "I don't have enough information in the sources to answer that."

SYSTEM_PROMPT = f"""You are a market-intelligence assistant for traders covering forex, crypto and the Pakistan Stock Exchange (PSX).

Rules:
1. Answer ONLY from the numbered sources in the user message. Never use outside knowledge.
2. Cite every fact with its source number in square brackets, like [1] or [2][3].
3. Copy numbers, rates, prices and percentages exactly as written in the sources.
4. Mention when things happened (the source date) if the question is about events.
5. If sources disagree, prefer the most recent one and say so.
6. If the sources do not contain the answer, reply exactly: "{REFUSAL}"
7. Be concise: 2-5 sentences or a short bullet list. No investment advice."""


@dataclass
class Source:
    """One numbered source in the prompt; chunks of the same document are merged."""

    n: int
    doc_id: str
    title: str
    url: str
    publisher: str
    published_at: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    text: str = ""

    @property
    def relevance(self) -> float:
        return max(c.relevance for c in self.chunks)

    def to_dict(self) -> dict:
        return {
            "n": self.n, "doc_id": self.doc_id, "title": self.title, "url": self.url,
            "publisher": self.publisher, "published_at": self.published_at,
            "relevance": round(self.relevance, 4), "text": self.text,
            "chunk_ids": [c.payload["chunk_id"] for c in self.chunks],
        }


def _trim(text: str, max_tokens: int, count) -> str:
    """Cut text to roughly max_tokens, preferring a sentence boundary."""
    if count(text) <= max_tokens:
        return text
    cut = text[: max(1, int(len(text) * max_tokens / count(text)))]
    end = cut.rfind(". ")
    return (cut[: end + 1] if end > len(cut) * 0.6 else cut.rstrip()) + " ..."


def pack_sources(chunks: list[RetrievedChunk], budget: int, count) -> list[Source]:
    """Group chunks by document (best first) and fit them into the token budget.

    The best chunks come first, so when the budget runs out it is the weakest
    evidence that gets trimmed or dropped.
    """
    by_doc: dict[str, Source] = {}
    for c in chunks:
        p = c.payload
        if p["doc_id"] not in by_doc:
            by_doc[p["doc_id"]] = Source(len(by_doc) + 1, p["doc_id"], p["title"], p["url"],
                                         p["publisher"], p["published_at"][:10])
        by_doc[p["doc_id"]].chunks.append(c)

    sources, used = [], 0
    for src in by_doc.values():
        # Inside one document keep reading order, not score order.
        parts = [c.payload["text"] for c in sorted(src.chunks, key=lambda c: c.payload["chunk_idx"])]
        text = "\n...\n".join(parts)
        header = f"[{src.n}] {src.title} ({src.publisher}, {src.published_at})\n"
        remaining = budget - used - count(header)
        if remaining < 60:  # not worth a fragment
            break
        src.text = _trim(text, remaining, count)
        used += count(header) + count(src.text)
        sources.append(src)
    return sources


def build_messages(question: str, sources: list[Source], now: datetime) -> list[Message]:
    blocks = "\n\n".join(f"[{s.n}] {s.title} ({s.publisher}, {s.published_at})\n{s.text}" for s in sources)
    user = (f"Today is {now:%d %B %Y}.\n\nSources:\n\n{blocks}\n\n"
            f"Question: {question}\n\nAnswer with citations:")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
