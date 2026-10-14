"""Retrieval evaluation: does the right article show up, and how high?

Metrics (doc-level, a hit counts if its title contains any labelled substring):
  Hit@1  - share of questions whose #1 result is relevant
  Hit@5  - share with a relevant result anywhere in the top 5 (what the LLM will see)
  MRR    - mean of 1/rank of the first relevant result (rewards ranking it higher)
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from rag.config import ROOT
from rag.retrieval.retriever import Retriever, RetrieverConfig

QUESTIONS = ROOT / "eval" / "retrieval_questions.jsonl"

# Questions the corpus cannot answer. The first group is unrelated (the retrieval gate
# should refuse); the second is on-domain but absent (the LLM itself must refuse).
OFF_TOPIC = [
    "What is a good recipe for chicken biryani?",
    "Who won the 2018 FIFA World Cup final?",
    "How do I reverse a linked list in Python?",
    "What is the capital of Australia?",
    "How many moons does Jupiter have?",
    "What are the symptoms of dengue fever?",
    "What was the Swiss National Bank's policy rate decision in 1995?",
    "What is the dividend yield of Lucky Cement on the PSX in 2010?",
]

CONFIGS: dict[str, RetrieverConfig] = {
    "bm25": RetrieverConfig(mode="bm25", use_plan=False, rerank=False, recency=False, diversify=False),
    "dense": RetrieverConfig(mode="dense", use_plan=False, rerank=False, recency=False, diversify=False),
    "hybrid": RetrieverConfig(mode="hybrid", use_plan=False, rerank=False, recency=False, diversify=False),
    "hybrid+rerank": RetrieverConfig(mode="hybrid", use_plan=False, rerank=True, recency=False, diversify=False),
    "rerank+filters": RetrieverConfig(mode="hybrid", use_plan=True, rerank=True, recency=False, diversify=True),
    "full pipeline": RetrieverConfig(mode="hybrid", use_plan=True, rerank=True, recency=True, diversify=True),
}


@dataclass
class EvalRow:
    config: str
    hit1: float
    hit5: float
    mrr: float
    ms_per_query: float
    misses: list[str]
    ranks: dict[str, int | None]


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def first_relevant_rank(titles: list[str], relevant: list[str]) -> int | None:
    rel = [r.lower() for r in relevant]
    for rank, title in enumerate(titles, 1):
        if any(r in title.lower() for r in rel):
            return rank
    return None


def evaluate(retriever: Retriever, configs: dict[str, RetrieverConfig] | None = None,
             questions: list[dict] | None = None, k: int = 10) -> list[EvalRow]:
    questions = questions or load_questions()
    rows = []
    for name, cfg in (configs or CONFIGS).items():
        hit1 = hit5 = mrr = 0.0
        misses = []
        ranks: dict[str, int | None] = {}
        t0 = time.perf_counter()
        for q in questions:
            result = retriever.retrieve(q["question"], k=k, config=cfg)
            rank = first_relevant_rank([c.payload["title"] for c in result.chunks], q["relevant"])
            ranks[q["question"]] = rank
            if rank:
                hit1 += rank == 1
                hit5 += rank <= 5
                mrr += 1 / rank
            if not rank or rank > 5:
                misses.append(q["question"])
        n = len(questions)
        rows.append(EvalRow(name, hit1 / n, hit5 / n, mrr / n, (time.perf_counter() - t0) * 1000 / n, misses, ranks))
    return rows
