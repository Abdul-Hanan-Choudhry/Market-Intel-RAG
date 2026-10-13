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
    llm_repo: str = "bartowski/Llama-3.2-3B-Instruct-GGUF"
    llm_file: str = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    llm_ctx: int = 4096
    llm_threads: int = 4

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
