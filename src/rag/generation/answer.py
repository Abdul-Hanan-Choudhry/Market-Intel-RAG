"""Retrieval-augmented answering: retrieve -> gate -> prompt -> stream -> check citations.

`stream()` yields events so the CLI, the API (SSE) and the UI can all show progress:
    {"type": "retrieval", ...}   plan + numbered sources, before the LLM starts
    {"type": "token", "text": ...}  one piece of the answer
    {"type": "done", "answer": {...}}  final answer with citations and timings
"""

import queue
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rag.config import settings
from rag.generation.llm import LLM, Busy, GenerationStats, get_llm
from rag.generation.prompt import REFUSAL, Source, build_messages, pack_sources
from rag.index.vector_store import SearchFilters
from rag.retrieval.retriever import RetrievalResult, Retriever

_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _with_stall_timeout(gen: Iterator, timeout_s: float) -> Iterator:
    """Run `gen` on a worker thread and raise TimeoutError if it stops producing items.

    llama.cpp can occasionally stall (e.g. starved of CPU by other processes) without
    raising a Python exception - the generator simply never yields again. A plain
    `for x in gen` can't detect that because it blocks forever on the next item. Running
    the generator on its own thread lets us use `queue.get(timeout=...)` as a watchdog.
    Note: if the C call really is stuck, the worker thread is leaked (not killable from
    Python) until the process restarts - but the caller gets a timely error either way.
    """
    q: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            for item in gen:
                q.put(("item", item))
            q.put(("done", None))
        except Exception as exc:  # noqa: BLE001 - forwarded to the consumer, not swallowed
            q.put(("error", exc))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        try:
            kind, value = q.get(timeout=timeout_s)
        except queue.Empty as exc:
            raise TimeoutError(f"no output for {timeout_s:.0f}s - the model may be stuck "
                                f"(try restarting `rag serve`)") from exc
        if kind == "item":
            yield value
        elif kind == "error":
            raise value
        else:
            return


def parse_citations(text: str) -> list[int]:
    """[1], [2][3] and [1, 4] -> sorted unique source numbers."""
    found = {int(n) for group in _CITATION.findall(text) for n in group.split(",")}
    return sorted(found)


def is_refusal(text: str) -> bool:
    return REFUSAL.lower().rstrip(".") in text.lower()


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Source]
    cited: list[int] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None
    plan: dict = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)
    generation: dict = field(default_factory=dict)
    model: str = ""

    @property
    def warnings(self) -> list[str]:
        w = []
        if self.invalid_citations:
            w.append(f"cites sources that do not exist: {self.invalid_citations}")
        if not self.refused and not self.cited:
            w.append("answer has no citations - verify against the sources")
        return w

    def to_dict(self) -> dict:
        return {
            "question": self.question, "answer": self.text, "refused": self.refused,
            "refusal_reason": self.refusal_reason, "cited": self.cited,
            "invalid_citations": self.invalid_citations, "warnings": self.warnings,
            "sources": [s.to_dict() for s in self.sources], "plan": self.plan,
            "timings_ms": {k: round(v) for k, v in self.timings_ms.items()},
            "generation": self.generation, "model": self.model,
        }


def _plan_dict(result: RetrievalResult) -> dict:
    p = result.plan
    return {"search_text": p.search_text, "description": p.describe(), "notes": p.notes,
            "time_sensitive": p.time_sensitive, "n_candidates": result.n_candidates,
            "best_relevance": round(result.best_relevance, 4)}


class Answerer:
    def __init__(self, retriever: Retriever | None = None, llm: LLM | None = None):
        self.retriever = retriever or Retriever()
        self._llm = llm

    @property
    def llm(self) -> LLM:
        if self._llm is None:  # loading the GGUF takes seconds; only do it when needed
            self._llm = get_llm()
        return self._llm

    @property
    def llm_name(self) -> str | None:
        return self._llm.name if self._llm else None

    def stream(self, question: str, k: int | None = None, filters: SearchFilters | None = None,
               now: datetime | None = None) -> Iterator[dict]:
        now = now or datetime.now(UTC)
        t0 = time.perf_counter()
        result = self.retriever.retrieve(question, k=k or settings.answer_k, extra_filters=filters, now=now)
        timings = {f"retrieval_{name}": ms for name, ms in result.timings_ms.items()}
        plan = _plan_dict(result)

        # Gate 1: if the reranker says nothing is relevant, an LLM can only hallucinate.
        if not result.chunks or result.best_relevance < settings.refuse_below:
            yield {"type": "retrieval", "plan": plan, "sources": []}
            timings["total"] = (time.perf_counter() - t0) * 1000
            answer = Answer(question, REFUSAL, [], refused=True, plan=plan, timings_ms=timings,
                            refusal_reason=f"no relevant sources (best relevance "
                                           f"{result.best_relevance:.3f} < {settings.refuse_below})")
            yield {"type": "done", "answer": answer.to_dict()}
            return

        sources = pack_sources(result.chunks, settings.context_token_budget, self.llm.count_tokens)
        yield {"type": "retrieval", "plan": plan, "sources": [s.to_dict() for s in sources]}

        messages = build_messages(question, sources, now)
        stats = GenerationStats()
        parts = []
        try:
            raw = self.llm.stream(messages, stats)
            for token in _with_stall_timeout(raw, settings.llm_stall_timeout_s):
                parts.append(token)
                yield {"type": "token", "text": token}
        except Busy as exc:
            timings["total"] = (time.perf_counter() - t0) * 1000
            yield {"type": "busy", "message": str(exc)}
            return
        except TimeoutError as exc:
            timings["total"] = (time.perf_counter() - t0) * 1000
            yield {"type": "error", "message": str(exc), "partial_answer": "".join(parts).strip()}
            return
        text = "".join(parts).strip()

        cited = parse_citations(text)
        valid = {s.n for s in sources}
        timings["llm_first_token"] = stats.time_to_first_token_ms
        timings["llm_total"] = stats.total_ms
        timings["total"] = (time.perf_counter() - t0) * 1000
        refused = is_refusal(text)
        answer = Answer(
            question, text, sources,
            cited=[n for n in cited if n in valid],
            invalid_citations=[n for n in cited if n not in valid],
            refused=refused, refusal_reason="model found no answer in the sources" if refused else None,
            plan=plan, timings_ms=timings, generation=stats.to_dict(), model=self.llm.name,
        )
        yield {"type": "done", "answer": answer.to_dict()}

    def answer(self, question: str, **kwargs) -> dict:
        final = {}
        for event in self.stream(question, **kwargs):
            if event["type"] == "done":
                final = event["answer"]
        return final
