"""Streamlit chat UI. It only talks HTTP to the API (`rag serve`), never to the models.

Run: rag ui   (or: streamlit run ui/app.py)
"""

import json
import os
import re
from collections.abc import Iterator

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
MARKETS = ["forex", "crypto", "psx", "macro"]
EXAMPLES = [
    "What does the IMF expect for Pakistan's inflation and GDP growth?",
    "How did the KSE-100 close this week?",
    "What did the Bank of England decide on interest rates in September?",
    "Which crypto exchanges did Britain sanction over Russia links?",
    "What is the outlook for the Japanese yen given intervention risk?",
]

st.set_page_config(page_title="Market Intelligence RAG", page_icon="📈", layout="wide")


@st.cache_data(ttl=30)
def get(path: str) -> dict | None:
    try:
        r = httpx.get(f"{API}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def sse_events(payload: dict) -> Iterator[dict]:
    """Parse Server-Sent Events: blocks of `event: x` / `data: {...}` separated by blank lines."""
    # No read timeout: on CPU the first token can take a minute or more.
    with httpx.stream("POST", f"{API}/ask/stream", json=payload,
                      timeout=httpx.Timeout(10, read=None)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                yield json.loads(line[6:])


def link_citations(text: str, sources: list[dict]) -> str:
    """Turn [2] into a clickable link to source 2."""
    urls = {s["n"]: s["url"] for s in sources}
    return re.sub(r"\[(\d+)\]", lambda m: f"[[{m.group(1)}]]({urls[int(m.group(1))]})"
                  if int(m.group(1)) in urls else m.group(0), text)


def render_sources(sources: list[dict], cited: list[int] | None = None) -> None:
    for s in sources:
        mark = "✅ cited" if cited and s["n"] in cited else ""
        with st.expander(f"[{s['n']}] {s['title']} — {s['publisher']}, {s['published_at']}  {mark}"):
            st.caption(f"relevance {s['relevance']:.2f} · [open article]({s['url']})")
            st.write(s["text"])


def render_details(answer: dict) -> None:
    with st.expander("How this answer was built"):
        t, g, plan = answer["timings_ms"], answer.get("generation") or {}, answer["plan"]
        cols = st.columns(4)
        cols[0].metric("Retrieval", f"{(t.get('retrieval_search', 0) + t.get('retrieval_rerank', 0)) / 1000:.1f} s")
        cols[1].metric("First token", f"{g.get('time_to_first_token_ms', 0) / 1000:.1f} s")
        cols[2].metric("Speed", f"{g.get('tokens_per_second', 0)} tok/s")
        cols[3].metric("Total", f"{t.get('total', 0) / 1000:.1f} s")
        st.markdown(f"**Model:** `{answer.get('model') or 'not called'}` · "
                    f"**candidates:** {plan.get('n_candidates')} · **best relevance:** {plan.get('best_relevance')}")
        st.markdown("**Query plan** (filters and boosts inferred from the question):")
        st.json(plan.get("description", {}), expanded=False)
        if answer.get("refusal_reason"):
            st.info(f"Refused: {answer['refusal_reason']}")


# ---------- sidebar ----------
with st.sidebar:
    st.header("📈 Market Intelligence")
    health = get("/health")
    if health:
        st.success(f"API online · {health['llm']}")
        if stats := get("/stats"):
            p = stats["pipeline"]
            st.caption(f"{p['documents']} documents · {p['chunks']} chunks · {stats['sources']} sources")
            st.caption(f"Newest: {(stats['newest_document'] or '')[:16].replace('T', ' ')} UTC")
            st.caption(" · ".join(f"{m} {n}" for m, n in stats["markets"].items()))
    else:
        st.error(f"API offline at {API}. Start it with `rag serve`.")

    st.subheader("Filters")
    markets = st.multiselect("Markets (empty = auto-detect)", MARKETS)
    days_label = st.selectbox("Time range", ["Auto-detect", "Last 24 hours", "Last 7 days", "Last 30 days"])
    days = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30}.get(days_label)
    k = st.slider("Chunks to retrieve", 2, 8, 4, help="More context = slower on CPU")
    st.caption("Answers come only from the indexed articles and cite their sources. Not investment advice.")
    if st.button("Clear chat"):
        st.session_state.messages = []

# ---------- chat ----------
st.title("Ask the market news")
st.caption("Forex · Crypto · PSX — local Llama 3.2 on CPU, hybrid search + reranking over today's news")

st.session_state.setdefault("messages", [])
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            a = msg["answer"]
            st.markdown(link_citations(a["answer"], a["sources"]))
            for w in a.get("warnings", []):
                st.warning(w)
            render_sources(a["sources"], a["cited"])
            render_details(a)

if not st.session_state.messages:
    st.write("Try one of these:")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}"):
            st.session_state.pending = ex
            st.rerun()

question = st.chat_input("Ask about forex, crypto or the PSX...") or st.session_state.pop("pending", None)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        status = st.status("Searching documents...", expanded=False)
        out = st.empty()
        text, answer = "", None
        try:
            for event in sse_events({"question": question, "k": k, "markets": markets, "days": days}):
                if event["type"] == "retrieval":
                    n = len(event["sources"])
                    status.update(label=f"Found {n} sources · generating answer (first words take a while on CPU)..."
                                  if n else "No relevant sources found")
                elif event["type"] == "token":
                    text += event["text"]
                    out.markdown(text + "▌")
                elif event["type"] == "done":
                    answer = event["answer"]
                elif event["type"] == "error":
                    status.update(label="Stalled", state="error")
                    st.error(event["message"])
                    if event.get("partial_answer"):
                        st.caption(f"Partial output before the stall: {event['partial_answer']!r}")
        except httpx.HTTPError as exc:
            status.update(label="Failed", state="error")
            st.error(f"Could not reach the API: {exc}")
        if answer:
            status.update(label="Done", state="complete")
            out.markdown(link_citations(answer["answer"], answer["sources"]))
            for w in answer["warnings"]:
                st.warning(w)
            render_sources(answer["sources"], answer["cited"])
            render_details(answer)
            st.session_state.messages.append({"role": "assistant", "answer": answer})
        else:
            status.update(label="Failed", state="error")
