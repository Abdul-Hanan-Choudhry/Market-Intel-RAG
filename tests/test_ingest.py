from datetime import UTC, datetime

from rag.ingest.connectors.base import SourceConfig, canonical_url, doc_id
from rag.ingest.connectors.rss import RSSConnector
from rag.ingest.models import DocType, Market, RawDocument
from rag.ingest.store import Catalog
from rag.ingest.tagging import extract_instruments, tag_markets


def make_doc(**kw) -> RawDocument:
    now = datetime(2026, 10, 13, tzinfo=UTC)
    base = {"id": "abc", "source": "test", "publisher": "Test", "doc_type": DocType.NEWS, "url": "https://x.com/a",
                "title": "Bitcoin rallies", "summary": "BTC up 5%", "published_at": now, "fetched_at": now}
    return RawDocument(**{**base, **kw})


def test_canonical_url_strips_tracking_and_www():
    a = canonical_url("https://www.CoinDesk.com/markets/btc/?utm_source=rss&utm_medium=x#top")
    b = canonical_url("https://coindesk.com/markets/btc")
    assert a == b
    assert doc_id(a) == doc_id(b)


def test_canonical_url_keeps_meaningful_query():
    assert "id=42" in canonical_url("https://example.com/news?id=42&utm_campaign=z")


def test_single_passing_mention_does_not_tag_market():
    body = "The hardware-wallet maker said keys were sent over the network. Any currency held was at risk."
    assert Market.FOREX not in tag_markets("Ledger reports spy chip", body)


def test_title_mention_tags_market():
    assert tag_markets("EUR/USD climbs above 1.10") >= {Market.FOREX}
    assert tag_markets("PSX gains 400 points as KSE-100 rebounds") >= {Market.PSX}
    assert tag_markets("SBP keeps policy rate unchanged") >= {Market.MACRO}


def test_case_sensitive_acronyms():
    assert Market.MACRO not in tag_markets("Investors are fed up with volatility")


def test_extract_instruments():
    text = "Bitcoin and ether slid while USD/PKR held steady and EURUSD fell."
    assert extract_instruments(text) == ["BTC", "ETH", "EUR/USD", "USD/PKR"]


def test_catalog_upsert_lifecycle(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    doc = make_doc()
    assert cat.upsert(doc) == "new"
    assert cat.upsert(doc) == "unchanged"
    assert cat.upsert(doc.model_copy(update={"summary": "BTC up 7%"})) == "updated"
    row = cat.conn.execute("SELECT version FROM documents WHERE id='abc'").fetchone()
    assert row["version"] == 2


RSS_FIXTURE = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>Rupee gains against dollar</title>
<link>https://www.example.pk/story/1?utm_source=feed</link>
<pubDate>Tue, 13 Oct 2026 08:28:47 +0500</pubDate>
<description>&lt;p&gt;The PKR rose in the interbank market.&lt;/p&gt;</description></item>
<item><title>No link item</title></item>
</channel></rss>"""


class FakeFetcher:
    def get(self, url, **kw):
        return type("R", (), {"content": RSS_FIXTURE})()


def test_rss_connector_rejects_html_error_page():
    import pytest

    class HtmlFetcher:
        def get(self, url, **kw):
            return type("R", (), {"content": b"<!DOCTYPE html><html><title>Not Found</title></html>"})()

    cfg = SourceConfig("x", "X")
    with pytest.raises(ValueError, match="not a valid feed"):
        list(RSSConnector(cfg, "https://example.com/feed").fetch(HtmlFetcher()))


def test_rss_connector_parses_and_normalises_dates():
    cfg = SourceConfig("pk", "Example", region="pk", markets=(Market.FOREX,))
    docs = list(RSSConnector(cfg, "https://example.pk/feed").fetch(FakeFetcher()))
    assert len(docs) == 1
    d = docs[0]
    assert d.summary == "The PKR rose in the interbank market."
    assert d.published_at == datetime(2026, 10, 13, 3, 28, 47, tzinfo=UTC)
    assert d.id == doc_id(canonical_url("https://example.pk/story/1"))
    assert not d.date_inferred
