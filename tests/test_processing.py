from datetime import UTC, datetime, timedelta

from rag.ingest.models import DocType, Market, RawDocument
from rag.ingest.store import Catalog
from rag.processing import dedup
from rag.processing import pipeline as processing
from rag.processing.chunk import MAX_TOKENS, chunk_text, count_tokens
from rag.processing.clean import clean_text

T0 = datetime(2026, 10, 13, 9, tzinfo=UTC)

PSX_REPORT = (
    "The benchmark KSE-100 Index gained {pts} points during trading on Tuesday as buying returned. "
    "Buying was observed in key sectors, including automobile assemblers, cement, commercial banks, "
    "oil and gas exploration companies and OMCs. Index-heavy stocks, including LUCK, DGKC, HBL, MCB, "
    "MEBL, NBP, OGDC, MARI and PSO, traded in the green. On Monday, the PSX witnessed heavy selling as "
    "domestic political uncertainty weighed on sentiment and investors booked profits across the board."
)


def doc(id_: str, text: str, published: datetime = T0, title: str = "PSX report") -> RawDocument:
    return RawDocument(id=id_, source="t", publisher="Business Recorder", doc_type=DocType.NEWS,
                       url=f"https://x.pk/{id_}", title=title, content=text, published_at=published,
                       fetched_at=published, markets=[Market.PSX])


def test_clean_text_removes_boilerplate_footnotes_and_repeated_title():
    raw = ("Bitcoin rallies\nBitcoin rose 5%.[12]\nAdvertisement\nThe post Bitcoin rallies appeared first on "
           "Decrypt.\nBitcoin rose 5%.\n  Traders   cheered.  ")
    assert clean_text(raw, "Bitcoin rallies") == "Bitcoin rose 5%.\nTraders cheered."


def test_short_text_is_one_chunk():
    chunks = chunk_text("Rupee gains against the dollar.\nSBP reserves rose.")
    assert len(chunks) == 1
    assert chunks[0].text == "Rupee gains against the dollar.\nSBP reserves rose."


def test_long_text_chunks_respect_limits_and_overlap():
    paragraphs = [f"Paragraph {i}. The central bank kept its policy rate unchanged at {i} percent. "
                  "Inflation expectations remain anchored according to the committee." for i in range(60)]
    chunks = chunk_text("\n".join(paragraphs))
    assert len(chunks) > 3
    assert all(c.n_tokens <= MAX_TOKENS for c in chunks)
    first_sentence_of_second = chunks[1].text.split("\n")[0]
    assert first_sentence_of_second in chunks[0].text  # overlap carried over


def test_headings_become_sections():
    text = ("Monetary policy decision\n" + "The Committee voted to maintain Bank Rate at 3.75%. " * 5 +
            "\nFinancial stability\n" + "Banks remain well capitalised and resilient to severe stress. " * 5)
    chunks = chunk_text(text)
    assert [c.section for c in chunks] == ["Monetary policy decision", "Financial stability"]


def test_oversized_paragraph_is_split():
    chunks = chunk_text(" ".join(["The yen weakened sharply against the dollar."] * 200))
    assert all(count_tokens(c.text) <= MAX_TOKENS for c in chunks)


def test_minhash_estimates_similarity():
    a = PSX_REPORT.format(pts=900)
    b = PSX_REPORT.format(pts=347)
    c = "Bitcoin ETF inflows hit a record as institutional demand surged across US spot products this week."
    assert dedup.similarity(dedup.minhash(a), dedup.minhash(b)) >= dedup.THRESHOLD
    assert dedup.similarity(dedup.minhash(a), dedup.minhash(c)) < 0.2


def test_newer_version_supersedes_older(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    morning = doc("morning", PSX_REPORT.format(pts=944), T0)
    close = doc("close", PSX_REPORT.format(pts=347), T0 + timedelta(hours=6))
    other = doc("btc", "Bitcoin ETF inflows hit a record as institutional demand surged. " * 3, T0, "BTC ETFs")
    for d in (morning, close, other):
        cat.upsert(d)

    counts = processing.run(cat)
    assert counts["superseded"] == 1
    state = {r["doc_id"]: dict(r) for r in cat.conn.execute("SELECT * FROM doc_state")}
    assert state["morning"]["duplicate_of"] == "close"
    assert state["morning"]["n_chunks"] == 0
    assert state["close"]["n_chunks"] == 1 and state["btc"]["n_chunks"] == 1

    assert processing.run(cat)["seen"] == 0  # incremental: nothing changed, nothing to do


def test_too_short_docs_are_skipped(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    cat.upsert(doc("x", "", title="BOJ stats"))
    assert processing.run(cat)["too_short"] == 1
