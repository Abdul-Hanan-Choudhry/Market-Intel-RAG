"""Source registry. Adding a feed = adding one line here.

All feeds below were verified reachable on 2026-10-13. Sources that block automated
access (SBP via Cloudflare, PSX data portal via reCAPTCHA) go through the inbox connector.
"""

from rag.ingest.connectors.base import Connector, SourceConfig
from rag.ingest.connectors.finnhub import FinnhubNewsConnector
from rag.ingest.connectors.inbox import InboxConnector
from rag.ingest.connectors.rss import RSSConnector
from rag.ingest.models import DocType
from rag.ingest.models import Market as M

CB = DocType.CENTRAL_BANK


def build_connectors() -> dict[str, Connector]:
    rss = [
        # --- Forex ---
        (SourceConfig("fxstreet", "FXStreet", markets=(M.FOREX,)), "https://www.fxstreet.com/rss/news"),
        # --- Crypto ---
        (SourceConfig("coindesk", "CoinDesk", markets=(M.CRYPTO,)), "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        (SourceConfig("decrypt", "Decrypt", markets=(M.CRYPTO,)), "https://decrypt.co/feed"),
        (SourceConfig("bitcoinmagazine", "Bitcoin Magazine", markets=(M.CRYPTO,)), "https://bitcoinmagazine.com/feed"),
        # --- Pakistan / PSX ---
        (SourceConfig("brecorder_markets", "Business Recorder", region="pk", require_relevance=True, fulltext=False),
         "https://www.brecorder.com/feeds/markets"),
        (SourceConfig("brecorder_business", "Business Recorder", region="pk", require_relevance=True, fulltext=False),
         "https://www.brecorder.com/feeds/business-finance"),
        (SourceConfig("nation_business", "The Nation", region="pk", require_relevance=True),
         "https://www.nation.com.pk/rss/business"),
        (SourceConfig("dawn_business", "Dawn", region="pk", require_relevance=True), "https://www.dawn.com/feeds/business"),
        (SourceConfig("tribune_business", "Express Tribune", region="pk", require_relevance=True),
         "https://tribune.com.pk/feed/business"),
        (SourceConfig("propakistani", "ProPakistani", region="pk", require_relevance=True),
         "https://propakistani.pk/category/business/feed/"),
        # --- Central banks ---
        (SourceConfig("fed_monetary", "Federal Reserve", CB, "us", (M.MACRO, M.FOREX)),
         "https://www.federalreserve.gov/feeds/press_monetary.xml"),
        (SourceConfig("ecb_press", "European Central Bank", CB, "eu", (M.MACRO, M.FOREX)),
         "https://www.ecb.europa.eu/rss/press.html"),
        (SourceConfig("boe_news", "Bank of England", CB, "uk", (M.MACRO, M.FOREX), require_relevance=True),
         "https://www.bankofengland.co.uk/rss/news"),
        (SourceConfig("boj_whatsnew", "Bank of Japan", CB, "jp", (M.MACRO, M.FOREX), require_relevance=True),
         "https://www.boj.or.jp/en/rss/whatsnew.xml"),
    ]
    connectors: dict[str, Connector] = {cfg.name: RSSConnector(cfg, url) for cfg, url in rss}

    for category, markets, relevance in (
        ("forex", (M.FOREX,), False),
        ("crypto", (M.CRYPTO,), False),
        ("general", (), True),
    ):
        cfg = SourceConfig(f"finnhub_{category}", "Finnhub", markets=markets, require_relevance=relevance)
        connectors[cfg.name] = FinnhubNewsConnector(cfg, category)

    connectors["inbox"] = InboxConnector(SourceConfig("inbox", "manual", fulltext=False))
    return connectors
