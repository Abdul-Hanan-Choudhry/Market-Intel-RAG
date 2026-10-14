"""LLM backends behind one tiny interface, so the RAG code never knows which one runs.

- LocalLlama: loads the GGUF file in-process with llama.cpp (CPU, no server needed).
- OpenAICompatible: any server speaking the OpenAI chat API - `llama-server` from
  llama.cpp, Ollama, vLLM on a GPU box, or a hosted API. Switch with LLM_BACKEND in .env.
"""

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from rag.config import settings

Message = dict[str, str]


@dataclass
class GenerationStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    time_to_first_token_ms: float = 0.0
    total_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def tokens_per_second(self) -> float:
        gen_ms = self.total_ms - self.time_to_first_token_ms
        return self.completion_tokens / (gen_ms / 1000) if gen_ms > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "time_to_first_token_ms": round(self.time_to_first_token_ms),
            "total_ms": round(self.total_ms),
            "tokens_per_second": round(self.tokens_per_second, 1),
        }


class LLM(Protocol):
    name: str

    def count_tokens(self, text: str) -> int: ...

    def stream(self, messages: list[Message], stats: GenerationStats,
               max_tokens: int | None = None, temperature: float | None = None) -> Iterator[str]: ...


class LocalLlama:
    def __init__(self, model_path: str | None = None):
        from llama_cpp import Llama

        path = model_path or str(settings.models_dir / settings.llm_file)
        self.name = f"local:{settings.llm_file}"
        # n_batch = how many prompt tokens are processed per step; bigger is faster on CPU up to a point.
        self.llm = Llama(model_path=path, n_ctx=settings.llm_ctx, n_threads=settings.llm_threads,
                         n_batch=512, verbose=False)
        # llama.cpp keeps one KV cache per model instance, so only one generation at a time.
        self.lock = threading.Lock()

    def count_tokens(self, text: str) -> int:
        return len(self.llm.tokenize(text.encode(), add_bos=False, special=True))

    def stream(self, messages: list[Message], stats: GenerationStats,
               max_tokens: int | None = None, temperature: float | None = None) -> Iterator[str]:
        with self.lock:
            t0 = time.perf_counter()
            stats.prompt_tokens = sum(self.count_tokens(m["content"]) for m in messages)
            chunks = self.llm.create_chat_completion(
                messages=messages, stream=True,
                max_tokens=max_tokens or settings.llm_max_tokens,
                temperature=settings.llm_temperature if temperature is None else temperature,
                top_p=0.9, repeat_penalty=1.1,
            )
            for chunk in chunks:
                delta = chunk["choices"][0]["delta"].get("content")
                if not delta:
                    continue
                if stats.completion_tokens == 0:
                    stats.time_to_first_token_ms = (time.perf_counter() - t0) * 1000
                stats.completion_tokens += 1
                yield delta
            stats.total_ms = (time.perf_counter() - t0) * 1000


class OpenAICompatible:
    def __init__(self) -> None:
        from openai import OpenAI

        self.client = OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key)
        self.name = f"openai:{settings.openai_model}@{settings.openai_base_url}"

    def count_tokens(self, text: str) -> int:
        return len(text) // 4  # rough; good enough for context budgeting

    def stream(self, messages: list[Message], stats: GenerationStats,
               max_tokens: int | None = None, temperature: float | None = None) -> Iterator[str]:
        t0 = time.perf_counter()
        stats.prompt_tokens = sum(self.count_tokens(m["content"]) for m in messages)
        response = self.client.chat.completions.create(
            model=settings.openai_model, messages=messages, stream=True,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=settings.llm_temperature if temperature is None else temperature,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if not delta:
                continue
            if stats.completion_tokens == 0:
                stats.time_to_first_token_ms = (time.perf_counter() - t0) * 1000
            stats.completion_tokens += 1
            yield delta
        stats.total_ms = (time.perf_counter() - t0) * 1000


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    return OpenAICompatible() if settings.llm_backend == "openai" else LocalLlama()
