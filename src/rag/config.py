import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    data_dir: Path = ROOT / "data"
    models_dir: Path = ROOT / "models"
    fastembed_cache: Path = ROOT / ".cache" / "fastembed"

    contact: str = "anonymous"
    finnhub_api_key: str = ""
    marketaux_api_key: str = ""

    qdrant_mode: Literal["local", "server"] = "local"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "market_intel"

    embed_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # 3B is the default: noticeably more reliable than the 1B model at keeping multiple
    # numbers/years straight in dense passages (the 1B model occasionally attaches the
    # right figure to the wrong year). ~3x slower on CPU (~20 tok/s reading, ~4 tok/s
    # writing vs ~37/~10 for 1B). Switch LLM_FILE to the 1B file in .env for speed instead.
    llm_repo: str = "bartowski/Llama-3.2-3B-Instruct-GGUF"
    llm_file: str = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    llm_ctx: int = 4096
    llm_threads: int = 4

    # Retrieval (Phase 4)
    rerank_candidates: int = 20
    rerank_max_chars: int = 1200
    recency_half_life_days: float = 7.0
    recency_weight: float = 0.25
    max_chunks_per_doc: int = 2

    # Generation (Phase 5). "local" runs the GGUF in-process; "openai" calls any
    # OpenAI-compatible server (llama.cpp server, Ollama, vLLM, Groq, OpenAI...).
    llm_backend: Literal["local", "openai"] = "local"
    llm_max_tokens: int = 300
    llm_temperature: float = 0.1
    # CPU prompt reading runs at ~20-37 tok/s depending on model size, so every 100 context
    # tokens costs several seconds before the first word appears. Raise these on a GPU /
    # remote backend, where this cost disappears.
    context_token_budget: int = 1200
    answer_k: int = 4
    # If no new token arrives for this long, something is stuck (e.g. CPU starved by other
    # processes) - report an error instead of hanging the UI forever.
    llm_stall_timeout_s: float = 150.0
    # How long a new request waits for a lock held by another in-flight generation before
    # giving up with a fast, clear "busy" message instead of queueing silently.
    llm_busy_wait_s: float = 3.0
    # Below this cross-encoder probability nothing retrieved is about the question: refuse
    # without calling the LLM (calibrated with `rag calibrate-refusal`).
    refuse_below: float = 0.02
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = "not-needed"
    openai_model: str = "llama3.2:3b"

    # Serving (Phase 6)
    api_url: str = "http://127.0.0.1:8000"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def catalog_path(self) -> Path:
        return self.raw_dir / "catalog.db"

    @property
    def user_agent(self) -> str:
        return f"EnterpriseRAG/0.1 (market-intelligence research; {self.contact})"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def qdrant_path(self) -> Path:
        return ROOT / "qdrant_storage" / "local"


settings = Settings()

os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
