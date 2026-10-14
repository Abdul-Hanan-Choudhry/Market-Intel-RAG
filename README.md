# Market Intel RAG

A Retrieval-Augmented Generation (RAG) assistant for traders covering **forex, crypto, and
the Pakistan Stock Exchange (PSX)**. It answers questions grounded in a continuously-updated
corpus of news, central bank releases, and regulatory filings — every answer is cited back
to a real source, and the model refuses to answer when nothing relevant was found.

Runs **fully local**: no GPU, no hosted LLM API, no data leaving the machine. An open-weight
model (Llama 3.2, quantized GGUF) runs on CPU via `llama.cpp`, with hybrid search (dense +
BM25) and cross-encoder reranking over a local Qdrant vector store.

```
"What does the IMF expect for Pakistan's inflation?"
  -> The latest inflation forecast for Pakistan is 9.9%, as projected by the IMF in its
     World Economic Outlook report [1][2].
```

## How it works

```
Ingest (RSS/APIs) -> Process (dedup, chunk) -> Index (embed -> Qdrant)
                                                        |
                                                        v
Frontend (React)  <--  API (FastAPI, SSE)  <--  Answer (retrieve -> rerank -> generate -> cite)
```

| Stage | What it does | Code |
|---|---|---|
| **Ingest** | Pulls from 18 RSS/API sources, extracts text, tags by market, dedupes by URL | `src/rag/ingest/` |
| **Process** | Cleans text, removes near-duplicates (MinHash), splits into token-aware chunks | `src/rag/processing/` |
| **Index** | Dense (BGE) + sparse (BM25) embeddings, synced into Qdrant | `src/rag/index/` |
| **Retrieve** | Query planning (market/date/region), hybrid search, cross-encoder reranking | `src/rag/retrieval/` |
| **Generate** | Packs sources into a prompt, streams the LLM, parses citations, refuses if ungrounded | `src/rag/generation/` |
| **Serve** | FastAPI (`/ask/stream` SSE, `/stats`, `/health`) + the React chat UI | `src/rag/api/`, `frontend/` |

## Quickstart

```powershell
git clone https://github.com/Abdul-Hanan-Choudhry/Market-Intel-RAG.git
cd Market-Intel-RAG
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.lock
copy .env.example .env                 # fill in CONTACT (and FINNHUB_API_KEY, optional)
python scripts/download_model.py       # downloads the default 3B GGUF (~1.9 GB)

rag ingest    # fetch documents
rag process   # clean, dedup, chunk
rag index     # embed + sync into Qdrant

rag serve     # terminal 1: API on :8000
```

```powershell
cd frontend
npm install
npm run dev   # terminal 2: chat UI on :5173
```

Or skip the UI and use the terminal directly:

```powershell
rag ask "What does the IMF expect for Pakistan's inflation?"
rag retrieve "KSE-100 weekly performance"   # retrieval only, no LLM
rag status                                  # pipeline stats
```

> **Qdrant's embedded ("local") mode allows only one process at a time.** Don't run CLI
> commands while `rag serve` is running — stop the server first, or set
> `QDRANT_MODE=server` with `docker-compose up -d` for concurrent access.

## Data sources

363 documents indexed (1,628 chunks) from 17 free, no-scraping sources: FXStreet (forex),
CoinDesk/Decrypt/Bitcoin Magazine + Finnhub (crypto), Business Recorder/Dawn/Express
Tribune/PropPakistani (PSX/Pakistan), and the Fed/ECB/BoE/BoJ (macro). `FINNHUB_API_KEY` is
the only key used by default (free tier).

## Why it's accurate, not just plausible

- **Two refusal gates.** Before generation, a low reranker score skips the LLM entirely
  ("I don't have enough information"). After generation, the model is required to say so
  itself if the sources don't answer the question — this stops confident hallucination.
- **3B model by default, not 1B.** The smaller model is 3x faster but occasionally mixed up
  which year a correct number belonged to in dense passages. Getting the number right
  matters more than shaving a minute off an answer for a trading tool.
- **Prompt forces concrete numbers.** The system prompt requires leading with the exact
  figure/date copied from the source — no vague paraphrasing ("roughly," "a bit higher").
- **Citations are checked, not trusted.** Every `[n]` in the answer is validated against the
  sources actually retrieved; invalid citations are flagged as a warning, not hidden.

Measured on 20 hand-labelled questions (`rag eval-retrieval --details`): the full pipeline
(hybrid search + reranking + query planning + recency/region boosts) gets **90% Hit@1,
100% Hit@5**, up from 60%/75% for BM25 alone.

## Project layout

```
src/rag/
  ingest/        connectors, tagging, polite fetcher, SQLite catalog
  processing/    clean, chunk, dedup
  index/         embeddings, Qdrant vector store
  retrieval/     query planning, reranker, retriever, evaluation
  generation/    prompt packing, LLM backends, Answerer
  api/           FastAPI app
  cli.py         ingest / process / index / search / ask / serve / ...
frontend/        React + TypeScript chat UI (see frontend/README.md)
eval/            labelled retrieval questions
tests/           49 tests covering ingestion -> generation -> API
```

## Configuration

All settings live in `.env` (see `.env.example` for every option, with comments). Nothing
beyond `CONTACT` is required to run the default ingestion sources. Swap `LLM_FILE` between
the 1B/3B models, or set `LLM_BACKEND=openai` to point at any OpenAI-compatible server
(Ollama, Groq, vLLM) instead of running the model in-process.

## Tests

```powershell
pytest -q                     # 49 tests, ~25-40s, no GPU/network required
ruff check src tests ui scripts
```
