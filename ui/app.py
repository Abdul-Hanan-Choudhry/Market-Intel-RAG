"""Streamlit chat UI. It only talks HTTP to the API (`rag serve`), never to the models.

Run: rag ui   (or: streamlit run ui/app.py)
"""

import json
import os
import re
import time
from collections.abc import Iterator

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
MARKETS = ["forex", "crypto", "psx", "macro"]
MARKET_COLOR = {"forex": "#f59e0b", "crypto": "#a78bfa", "psx": "#34d399", "macro": "#60a5fa"}
EXAMPLES = [
    ("📊", "What does the IMF expect for Pakistan's inflation and GDP growth?"),
    ("📈", "How did the KSE-100 close this week?"),
    ("🏦", "What did the Bank of England decide on interest rates in September?"),
    ("₿", "Which crypto exchanges did Britain sanction over Russia links?"),
    ("💴", "What is the outlook for the Japanese yen given intervention risk?"),
]

st.set_page_config(page_title="Market Intel · RAG", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

# ----------------------------------------------------------------------------------------
# Visual design: Streamlit's defaults look like a demo. This CSS block turns it into
# something closer to a real product - a dark "fintech terminal" aesthetic, card-based
# layout, colored market/relevance badges, and a few small animations. It targets
# Streamlit's stable `data-testid` attributes rather than its internal (version-fragile)
# class names, so it should survive Streamlit upgrades reasonably well.
# ----------------------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
code, pre, .mono { font-family: 'JetBrains Mono', monospace !important; }

#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.2rem; max-width: 1100px; }

/* ---- brand header ---- */
.brand-bar { display: flex; align-items: center; justify-content: space-between;
             padding: 0.9rem 1.4rem; margin-bottom: 1.4rem; border-radius: 16px;
             background: linear-gradient(135deg, #0f1b33 0%, #16233f 100%);
             border: 1px solid rgba(148,163,184,.15); }
.brand-title { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em;
               background: linear-gradient(90deg, #22d3ee, #818cf8);
               -webkit-background-clip: text; background-clip: text; color: transparent; }
.brand-sub { color: #94a3b8; font-size: 0.82rem; margin-top: 2px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px;
        border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.pill-ok { background: rgba(52,211,153,.12); color: #34d399; border: 1px solid rgba(52,211,153,.3); }
.pill-bad { background: rgba(248,113,113,.12); color: #f87171; border: 1px solid rgba(248,113,113,.3); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor;
       box-shadow: 0 0 8px currentColor; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* ---- sidebar ---- */
[data-testid="stSidebar"] { background: #0e1626; border-right: 1px solid rgba(148,163,184,.1); }
.kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0 14px; }
.kpi-card { background: rgba(148,163,184,.06); border: 1px solid rgba(148,163,184,.12);
            border-radius: 12px; padding: 10px 12px; }
.kpi-val { font-size: 1.25rem; font-weight: 700; color: #e2e8f0; line-height: 1.1; }
.kpi-label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: .04em; }
.market-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 4px; }
.mkt-badge { padding: 3px 10px; border-radius: 999px; font-size: 0.74rem; font-weight: 600; }

/* ---- chat ---- */
[data-testid="stChatMessage"] { background: rgba(148,163,184,.05); border: 1px solid rgba(148,163,184,.1);
                                 border-radius: 16px; padding: 4px 6px; margin-bottom: 10px; }
.cite-pill { display: inline-block; background: rgba(34,211,238,.14); color: #22d3ee;
             border: 1px solid rgba(34,211,238,.35); border-radius: 6px; padding: 0 6px;
             font-size: 0.78em; font-weight: 700; text-decoration: none !important; margin: 0 1px; }
.src-card { background: rgba(148,163,184,.05); border: 1px solid rgba(148,163,184,.12);
            border-radius: 12px; padding: 10px 14px; margin-bottom: 8px; }
.src-title { font-weight: 600; font-size: 0.92rem; }
.src-meta { color: #94a3b8; font-size: 0.78rem; margin-top: 2px; }
.rel-badge { float: right; padding: 2px 9px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }
.rel-hi { background: rgba(52,211,153,.14); color: #34d399; }
.rel-mid { background: rgba(251,191,36,.14); color: #fbbf24; }
.rel-lo { background: rgba(248,113,113,.14); color: #f87171; }

/* ---- suggestion chips ---- */
div[data-testid="stButton"] > button { border-radius: 999px !important; border: 1px solid rgba(148,163,184,.25) !important;
    background: rgba(148,163,184,.06) !important; color: #e2e8f0 !important; font-size: 0.86rem !important;
    padding: 0.5rem 1rem !important; transition: all .15s ease; }
div[data-testid="stButton"] > button:hover { border-color: #22d3ee !important; color: #22d3ee !important;
    background: rgba(34,211,238,.08) !important; }

/* ---- generating indicator ---- */
.thinking { display: inline-flex; gap: 4px; align-items: center; color: #94a3b8; font-size: 0.85rem; }
.thinking span.dot3 { width: 5px; height: 5px; border-radius: 50%; background: #22d3ee;
    animation: bounce 1.2s infinite; }
.thinking span.dot3:nth-child(2) { animation-delay: .2s; } .thinking span.dot3:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,80%,100% { transform: translateY(0); opacity:.4; } 40% { transform: translateY(-4px); opacity:1; } }

[data-testid="stChatInput"] textarea { border-radius: 14px !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=20)
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
    """Turn [2] into a styled, clickable pill linking to source 2."""
    urls = {s["n"]: s["url"] for s in sources}

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        return (f'<a class="cite-pill" href="{urls[n]}" target="_blank">{n}</a>' if n in urls else m.group(0))

    return re.sub(r"\[(\d+)\]", repl, text)


def rel_class(score: float) -> str:
    return "rel-hi" if score >= 0.7 else ("rel-mid" if score >= 0.3 else "rel-lo")


def render_sources(sources: list[dict], cited: list[int] | None = None) -> None:
    for s in sources:
        mark = " · ✅ cited" if cited and s["n"] in cited else ""
        st.markdown(
            f'<div class="src-card"><span class="rel-badge {rel_class(s["relevance"])}">'
            f'{s["relevance"]:.0%} match</span>'
            f'<div class="src-title">[{s["n"]}] {s["title"]}</div>'
            f'<div class="src-meta">{s["publisher"]} · {s["published_at"]}{mark} · '
            f'<a href="{s["url"]}" target="_blank" style="color:#60a5fa;">open article ↗</a></div></div>',
            unsafe_allow_html=True)
        with st.expander("Show source text"):
            st.write(s["text"])


def render_details(answer: dict) -> None:
    with st.expander("⚙️ How this answer was built"):
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


# ================================= header =================================
health = get("/health")
status_html = (f'<span class="pill pill-ok"><span class="dot"></span>Online · {health["llm"].split(":")[-1]}</span>'
              if health else '<span class="pill pill-bad"><span class="dot"></span>API offline</span>')
st.markdown(f"""
<div class="brand-bar">
  <div><div class="brand-title">📈 Market Intel</div>
       <div class="brand-sub">RAG over forex · crypto · PSX news — local SLM, hybrid search, cited sources</div></div>
  <div>{status_html}</div>
</div>""", unsafe_allow_html=True)

if not health:
    st.error(f"Can't reach the API at `{API}`. Start it with `rag serve`.")
    st.stop()

# ================================= sidebar =================================
with st.sidebar:
    st.markdown("### 🧭 Overview")
    if stats := get("/stats"):
        p = stats["pipeline"]
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-card"><div class="kpi-val">{p['documents']}</div><div class="kpi-label">Documents</div></div>
            <div class="kpi-card"><div class="kpi-val">{p['chunks']}</div><div class="kpi-label">Chunks</div></div>
            <div class="kpi-card"><div class="kpi-val">{stats['sources']}</div><div class="kpi-label">Sources</div></div>
            <div class="kpi-card"><div class="kpi-val">{p.get('indexed_docs', 0)}</div><div class="kpi-label">Indexed</div></div>
        </div>""", unsafe_allow_html=True)
        badges = "".join(f'<span class="mkt-badge" style="background:{MARKET_COLOR.get(m, "#64748b")}22;'
                         f'color:{MARKET_COLOR.get(m, "#64748b")};">{m} · {n}</span>'
                         for m, n in stats["markets"].items())
        st.markdown(f'<div class="market-badges">{badges}</div>', unsafe_allow_html=True)
        st.caption(f"Newest: {(stats['newest_document'] or '')[:16].replace('T', ' ')} UTC")

    st.divider()
    st.markdown("### 🔎 Filters")
    markets = st.multiselect("Markets", MARKETS, help="Empty = auto-detected from your question")
    days_label = st.selectbox("Time range", ["Auto-detect", "Last 24 hours", "Last 7 days", "Last 30 days"])
    days = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30}.get(days_label)
    k = st.slider("Chunks to retrieve", 2, 8, 3, help="More context = slower on CPU")

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption("Answers are grounded only in the indexed articles and always cite their "
              "sources. This is market *information*, not investment advice.")

# ================================= chat =================================
st.session_state.setdefault("messages", [])

if not st.session_state.messages:
    st.markdown("#### Ask about forex, crypto or the Pakistan Stock Exchange")
    st.caption("Try one of these, or type your own question below.")
    cols = st.columns(len(EXAMPLES))
    for col, (icon, ex) in zip(cols, EXAMPLES, strict=True):
        if col.button(f"{icon}  {ex[:34]}{'…' if len(ex) > 34 else ''}", key=ex, use_container_width=True):
            st.session_state.pending = ex
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍💼" if msg["role"] == "user" else "📈"):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            a = msg["answer"]
            st.markdown(link_citations(a["answer"], a["sources"]), unsafe_allow_html=True)
            for w in a.get("warnings", []):
                st.warning(w)
            if a["sources"]:
                with st.expander(f"📎 {len(a['sources'])} sources", expanded=False):
                    render_sources(a["sources"], a["cited"])
            render_details(a)

question = st.chat_input("Ask about forex, crypto or the PSX...") or st.session_state.pop("pending", None)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.write(question)
    with st.chat_message("assistant", avatar="📈"):
        status = st.status("Searching documents...", expanded=False)
        out = st.empty()
        t0 = time.perf_counter()
        text, answer, live_sources = "", None, []
        try:
            for event in sse_events({"question": question, "k": k, "markets": markets, "days": days}):
                if event["type"] == "retrieval":
                    live_sources = event["sources"]
                    n = len(live_sources)
                    status.update(label=f"Found {n} sources · generating (first words take longest on CPU)..."
                                  if n else "No relevant sources found")
                    if n:
                        out.markdown('<div class="thinking">Writing answer<span class="dot3"></span>'
                                     '<span class="dot3"></span><span class="dot3"></span></div>',
                                     unsafe_allow_html=True)
                elif event["type"] == "token":
                    text += event["text"]
                    out.markdown(link_citations(text, live_sources) + " ▌", unsafe_allow_html=True)
                elif event["type"] == "done":
                    answer = event["answer"]
                elif event["type"] == "busy":
                    status.update(label="Busy", state="error")
                    st.warning(event["message"])
                elif event["type"] == "error":
                    status.update(label="Stalled", state="error")
                    st.error(event["message"])
                    if event.get("partial_answer"):
                        st.caption(f"Partial output before the stall: {event['partial_answer']!r}")
        except httpx.HTTPError as exc:
            status.update(label="Failed", state="error")
            st.error(f"Could not reach the API: {exc}")
        if answer:
            status.update(label=f"Done in {time.perf_counter() - t0:.1f}s", state="complete")
            out.markdown(link_citations(answer["answer"], answer["sources"]), unsafe_allow_html=True)
            for w in answer["warnings"]:
                st.warning(w)
            if answer["sources"]:
                with st.expander(f"📎 {len(answer['sources'])} sources", expanded=True):
                    render_sources(answer["sources"], answer["cited"])
            render_details(answer)
            st.session_state.messages.append({"role": "assistant", "answer": answer})
        elif not answer:
            status.update(label="No answer", state="error")
