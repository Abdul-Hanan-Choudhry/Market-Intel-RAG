# Enterprise RAG — Market Intelligence for Traders

A local-first Retrieval-Augmented Generation system that answers questions about **forex,
crypto and the Pakistan Stock Exchange (PSX)** from a continuously-updated corpus of news,
central bank releases and regulatory filings — using an open-weight small language model
(Llama 3.2, quantized to GGUF) running entirely on a CPU, with hybrid search and reranking
over a local vector database.

Built as a portfolio project for forward-deployed / ML engineering roles: every component
(ingestion, dedup, chunking, hybrid retrieval, reranking, grounded generation, serving) is
implemented from scratch rather than wired together from a framework, and is covered by 47
automated tests.

```
"What does the IMF expect for Pakistan's inflation and GDP growth?"
  -> According to the sources, the IMF expects Pakistan's inflation rate to rise to
     9.9% in 2027 [1][2][3]. For GDP growth, the IMF projects it at 3.5% for 2026 and
     3.5% for 2027 [1][2].
  [1] brecorder.com/.../imf-sees-pakistans-inflation...
  [2] dawn.com/.../pakistans-growth-during-fy27...
```

## Why this exists

Most "RAG demo" projects either call a hosted LLM API or assume a GPU. This one is built
for the forward-deployed reality: a client's laptop with no GPU, no internet access to a
model provider, and data that must never leave the machine. Every design decision — the
model size, the context budget, the retrieval filters, the refusal threshold — was measured
against real constraints (a 4-core CPU, 20 GB RAM) rather than assumed.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌────────────┐
│  Ingestion   │ --> │  Processing  │ --> │    Index      │ --> │ Retrieval  │
│ RSS/Finnhub/ │     │ clean, dedup │     │ fastembed     │     │ hybrid     │
│ inbox + SQLite catalog│  chunk    │     │ (dense+BM25)  │     │ search +   │
│ (change detection)    │          │     │ -> Qdrant     │     │ rerank     │
└─────────────┘     └──────────────┘     └───────────────┘     └─────┬──────┘
                                                                       v
┌─────────────┐     ┌──────────────┐     ┌───────────────┐    ┌────────────┐
│ Streamlit UI │ <-- │  FastAPI     │ <-- │  Generation   │ <--│  (chunks)  │
│ chat + citations│  │ /ask/stream  │     │ grounded, cites│    │            │
│             │     │ (SSE)        │     │ [n], refuses   │    └────────────┘
└─────────────┘     └──────────────┘     └───────────────┘
```

| Layer | What it does | Key files |
|---|---|---|
| **Ingestion** | Polite fetching (robots.txt, throttling, retries) from 18 RSS/API sources, full-text extraction, market tagging, dedup by canonical URL, SQLite catalog with change detection | `src/rag/ingest/` |
| **Processing** | Clean text, near-duplicate detection (MinHash), token-aware chunking with contextual headers | `src/rag/processing/` |
| **Index** | Dense (BGE) + sparse (BM25) embeddings via `fastembed`, incremental sync into Qdrant | `src/rag/index/` |
| **Retrieval** | Query planning (market/date/region/acronyms), hybrid search with filter relaxation, cross-encoder reranking, recency + region boosts, per-document diversity | `src/rag/retrieval/` |
| **Generation** | Prompt packing within a token budget, streaming local/remote LLM, citation parsing, refusal gate | `src/rag/generation/` |
| **Serving** | FastAPI (`/health`, `/stats`, `/search`, `/ask`, `/ask/stream` SSE) + Streamlit chat UI | `src/rag/api/`, `ui/` |

## Data sources

363 documents indexed (1,628 chunks), 17 live sources, all free / no scraping of
protected sites:

- **Forex**: FXStreet (RSS)
- **Crypto**: CoinDesk, Decrypt, Bitcoin Magazine (RSS), Finnhub crypto news (API)
- **PSX / Pakistan**: Business Recorder, Dawn Business, Express Tribune Business,
  PropPakistani (RSS); an `inbox/` drop folder for PDFs from SBP, PSX, SECP (both sites
  block automated access with Cloudflare/reCAPTCHA — handled manually by design, not bypassed)
- **Central banks (macro)**: US Federal Reserve, ECB, Bank of England, Bank of Japan (RSS)
- **General market**: Finnhub general + forex news (API)

`FINNHUB_API_KEY` is the only API key currently used (free tier). `MARKETAUX_API_KEY` is
wired up but optional/unused.

## Quickstart

```powershell
git clone <repo> && cd Enterprise-Rag
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.lock            # pinned, reproducible
copy .env.example .env                      # fill in CONTACT and FINNHUB_API_KEY
python scripts/download_model.py            # downloads the default 3B GGUF (~1.9 GB)

rag ingest                                  # fetch documents into data/raw/catalog.db
rag process                                 # clean, dedup, chunk
rag index                                   # embed + sync into Qdrant

rag serve                                   # terminal 1: API on :8000
rag ui                                      # terminal 2: chat UI on :8501
```

Or skip the UI and use the terminal directly:

```powershell
rag ask "What does the IMF expect for Pakistan's inflation?"
rag ask "..." --show-prompt     # print the exact source text the model read
rag retrieve "..."              # retrieval only, no LLM, full scoring breakdown
rag search "KSE-100" --mode hybrid --market psx
rag status                      # pipeline stats
```

> **Note on Qdrant's embedded ("local") mode:** only one process may open
> `qdrant_storage/local` at a time. Don't run CLI commands (`rag ask`, `rag retrieve`, ...)
> in a separate terminal while `rag serve` is running — use the API/UI instead, or stop
> the server first. Set `QDRANT_MODE=server` with `docker-compose up -d` for true
> concurrent access.

## Evaluation

20 hand-labelled questions (`eval/retrieval_questions.jsonl`), scored by whether the
correct article is ranked #1 (Hit@1), in the top 5 (Hit@5), and by mean reciprocal rank:

| Configuration | Hit@1 | Hit@5 | MRR | Time/query |
|---|---|---|---|---|
| BM25 only | 60% | 75% | 0.690 | 176 ms |
| Dense only | 85% | 100% | 0.892 | 24 ms |
| Hybrid (BM25 + dense, RRF) | 75% | 95% | 0.841 | 183 ms |
| Hybrid + reranker | 85% | 100% | 0.904 | ~2 s |
| + query planning & filters | 90% | 100% | 0.942 | ~1.7 s |
| **Full pipeline** (+ recency/region boosts) | **90%** | **100%** | **0.942** | ~1.7 s |

Run it yourself: `rag eval-retrieval --details`

**Refusal calibration** (`rag calibrate-refusal`): on-topic questions score 0.46–1.00
relevance from the reranker; off-topic ones ("chicken biryani recipe", "capital of
Australia") score 0.0000–0.0012. The refusal threshold (`REFUSE_BELOW=0.02`) sits safely
between the two, so the system answers "I don't have enough information" without even
calling the LLM when nothing relevant was retrieved.

**Generation speed** on a 4-core / 8-thread CPU laptop, no GPU:

| Model | Prompt reading | Generation | Typical answer |
|---|---|---|---|
| Llama 3.2 **3B** Q4_K_M (default) | ~20 tok/s | ~4 tok/s | 60–105 s |
| Llama 3.2 **1B** Q4_K_M (`LLM_FILE=...`) | ~37 tok/s | ~10 tok/s | ~35 s |
| Any OpenAI-compatible backend (Groq, Ollama+GPU, llama-server) | — | — | ~1–5 s |

Because reading the prompt is the slow part, `CONTEXT_TOKEN_BUDGET` is tuned to ~1,200
tokens (4 chunks) rather than a larger window — doubling it would roughly double the wait
before the first word appears.

## Design decisions worth calling out

- **Hybrid retrieval, not just dense.** BM25 alone misses paraphrases; dense alone misses
  exact tickers/acronyms. Fusing both (Reciprocal Rank Fusion) and then reranking gives the
  best of both — measured, not assumed (see table above).
- **Filter relaxation.** Heuristic filters (market/date from the question) narrow search,
  but if they return too few candidates they're dropped progressively rather than returning
  an empty result.
- **Recency only when asked.** A blanket "newer is better" boost hurt accuracy on
  non-time-sensitive questions in testing; it's now gated on words like "latest"/"today".
- **Two refusal gates.** Before calling the LLM (reranker score too low → clearly off-topic),
  and after (the model itself says it doesn't know, e.g. for an on-topic but uncovered
  question) — because an ungrounded LLM will otherwise confidently hallucinate.
- **One LLM interface, two backends.** `LLM_BACKEND=local` runs llama.cpp in-process;
  `LLM_BACKEND=openai` talks to any OpenAI-compatible server (Ollama, llama-server, vLLM,
  Groq). Same prompt/retrieval code either way — this is how the same system would move
  from a laptop demo to a client's GPU box or a hosted API.
- **Stall watchdog.** A CPU-only LLM can occasionally stall if starved of cores by other
  processes. Generation runs on a worker thread with a timeout so a stuck model surfaces as
  an error within ~2.5 minutes instead of hanging the UI forever.
- **Near-duplicate detection.** Wire services often republish the same story; MinHash
  similarity (threshold 0.7, 4-day window) merges near-duplicates, keeping the newest
  version.

## Project layout

```
src/rag/
  ingest/        connectors (RSS, Finnhub, inbox), tagging, polite fetcher, SQLite catalog
  processing/    clean, chunk, MinHash dedup, pipeline
  index/         fastembed embedder, Qdrant vector store, indexing pipeline
  retrieval/     query planning, reranker, retriever, evaluation
  generation/    prompt packing, LLM backends (local/OpenAI-compatible), Answerer
  api/           FastAPI app (health/stats/search/ask/ask-stream)
  cli.py         typer CLI: ingest, process, index, search, retrieve, ask, serve, ui, ...
ui/app.py        Streamlit chat UI
scripts/         download_model.py, bench_llm.py, check_env.py (Phase 0 smoke test)
eval/            labelled retrieval questions
tests/           46+ tests: ingestion, processing, indexing, retrieval, generation, API
```

## Configuration

All settings live in `.env` (see `.env.example` for every option with comments), loaded via
`src/rag/config.py`. Nothing beyond `CONTACT` (for a polite crawler User-Agent) and
`FINNHUB_API_KEY` is required to run the ingestion sources used by default.

## Tests

```powershell
pytest -q            # 47 tests, ~25-45s (no GPU/network required; models mocked for API/generation tests)
ruff check src tests ui scripts
```
