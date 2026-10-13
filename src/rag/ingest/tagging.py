"""Rule-based market and instrument tagging.

Tags become Qdrant payload fields in Phase 3, which lets retrieval filter by market
("only crypto") before any vector math happens.
"""

import re

from rag.ingest.models import Market


def _terms(words: list[str], case_sensitive: bool = False) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", flags)


MARKET_PATTERNS: dict[Market, list[re.Pattern]] = {
    Market.CRYPTO: [
        _terms([
            "bitcoin", "ethereum", "ether", "crypto", "cryptocurrency", "cryptocurrencies",
            "stablecoin", "stablecoins", "tether", "solana", "ripple", "dogecoin", "binance",
            "coinbase", "defi", "blockchain", "altcoin", "altcoins", "memecoin", "web3",
        ]),
        _terms(["BTC", "ETH", "XRP", "SOL", "USDT", "USDC", "BNB", "ETF flows"], case_sensitive=True),
    ],
    Market.FOREX: [
        _terms([
            "forex", "currency", "currencies", "exchange rate", "dollar", "greenback", "euro",
            "yen", "sterling", "rupee", "yuan", "renminbi", "swiss franc", "loonie", "aussie",
            "interbank market", "open market rate", "remittances",
        ]),
        _terms(["FX", "DXY"], case_sensitive=True),
        re.compile(r"\b(?:EUR|USD|GBP|JPY|CHF|AUD|NZD|CAD|CNY|CNH|PKR|INR)\s?/\s?[A-Z]{3}\b"),
    ],
    Market.PSX: [
        _terms([
            "pakistan stock exchange", "karachi stock exchange", "kse-100", "kse 100", "kse100",
            "kmi-30", "all share index", "bourse",
        ]),
        _terms(["PSX", "SECP", "KSE"], case_sensitive=True),
    ],
    Market.MACRO: [
        _terms([
            "central bank", "monetary policy", "interest rate", "interest rates", "policy rate",
            "rate cut", "rate hike", "inflation", "federal reserve", "bank of england",
            "bank of japan", "state bank of pakistan", "treasury yields", "bond yields",
            "current account", "recession", "jobs report", "nonfarm payrolls", "economic activity",
        ]),
        _terms(["Fed", "FOMC", "ECB", "BoE", "BoJ", "SBP", "IMF", "CPI", "GDP"], case_sensitive=True),
    ],
}

_CRYPTO_SYMBOLS = {
    "bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "ether": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL", "xrp": "XRP", "ripple": "XRP", "dogecoin": "DOGE",
    "tether": "USDT", "usdt": "USDT", "usdc": "USDC", "bnb": "BNB", "cardano": "ADA",
}
_CRYPTO_RE = re.compile(r"\b(" + "|".join(_CRYPTO_SYMBOLS) + r")\b", re.IGNORECASE)
_PAIR_RE = re.compile(
    r"\b(EUR|USD|GBP|JPY|CHF|AUD|NZD|CAD|CNY|CNH|PKR|INR)\s?/?\s?(EUR|USD|GBP|JPY|CHF|AUD|NZD|CAD|CNY|CNH|PKR|INR)\b"
)


def _hits(market: Market, text: str) -> int:
    return sum(len(p.findall(text)) for p in MARKET_PATTERNS[market])


def tag_markets(title: str, body: str = "", min_body_hits: int = 2) -> set[Market]:
    """A market applies if the title mentions it, or the body mentions it repeatedly.

    A single passing mention ("...priced in dollars...") is not enough to call an
    article forex news; that noise would leak into filtered retrieval later.
    """
    return {m for m in MARKET_PATTERNS if _hits(m, title) or _hits(m, body) >= min_body_hits}


def extract_instruments(text: str) -> list[str]:
    found = {_CRYPTO_SYMBOLS[m.lower()] for m in _CRYPTO_RE.findall(text)}
    found |= {f"{a}/{b}" for a, b in _PAIR_RE.findall(text) if a != b}
    return sorted(found)
