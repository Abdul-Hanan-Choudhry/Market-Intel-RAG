"""Query understanding: turn a trader's question into search text + filters + boosts.

"How did the KSE-100 do this week?" becomes
    markets=[psx], since=now-7d, region boost=pk, time_sensitive=True
so the vector search only looks at the right slice of the index.

Hard filters (markets, dates) narrow the search; soft signals (region, instruments)
only nudge the ranking, because our tags are imperfect and a hard filter on an
imperfect tag silently hides good documents.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from rag.index.vector_store import SearchFilters
from rag.ingest.tagging import extract_instruments, tag_markets

# Domain glossary: documents often spell out what traders abbreviate (and vice versa).
# Appending the expansion lets BM25 match either form and gives the reranker the meaning.
GLOSSARY = {
    "FOMC": "Federal Open Market Committee",
    "Fed": "Federal Reserve",
    "ECB": "European Central Bank",
    "BoE": "Bank of England",
    "BOE": "Bank of England",
    "BoJ": "Bank of Japan",
    "BOJ": "Bank of Japan",
    "SBP": "State Bank of Pakistan",
    "RBI": "Reserve Bank of India",
    "MPC": "Monetary Policy Committee",
    "PSX": "Pakistan Stock Exchange",
    "SECP": "Securities and Exchange Commission of Pakistan",
    "IMF": "International Monetary Fund",
    "CPI": "consumer price inflation",
    "NFP": "nonfarm payrolls",
    "DXY": "US dollar index",
    "BTC": "bitcoin",
    "ETH": "ether",
}
_GLOSSARY_RE = re.compile(r"\b(" + "|".join(map(re.escape, GLOSSARY)) + r")\b")

_PK_TERMS = re.compile(
    r"\b(pakistan|pakistani|psx|kse[- ]?100|kmi[- ]?30|sbp|state bank|rupee|pkr|secp|karachi)\b", re.IGNORECASE
)
_TIME_SENSITIVE = re.compile(r"\b(latest|recent|recently|today|now|current|currently|so far|this week)\b", re.IGNORECASE)
_LAST_N = re.compile(r"\b(?:last|past) (\d{1,3}) (hour|day|week|month)s?\b", re.IGNORECASE)
_MONTH = re.compile(
    r"\b(" + "|".join(calendar.month_name[1:]) + r")(?:\s+(20\d\d))?\b", re.IGNORECASE
)
_RELATIVE = [
    (re.compile(r"\b(today|this morning|tonight)\b", re.IGNORECASE), timedelta(hours=30)),
    (re.compile(r"\byesterday\b", re.IGNORECASE), timedelta(days=2, hours=12)),
    (re.compile(r"\b(this week|past week)\b", re.IGNORECASE), timedelta(days=7)),
    (re.compile(r"\blast week\b", re.IGNORECASE), timedelta(days=14)),
    (re.compile(r"\b(this month|past month)\b", re.IGNORECASE), timedelta(days=31)),
]


@dataclass
class QueryPlan:
    question: str
    search_text: str = ""
    filters: SearchFilters = field(default_factory=SearchFilters)
    region: str | None = None
    instruments: list[str] = field(default_factory=list)
    time_sensitive: bool = False
    notes: list[str] = field(default_factory=list)

    def describe(self) -> dict:
        f = self.filters
        return {
            "search_text": self.search_text,
            "markets": f.markets,
            "since": f.since.isoformat() if f.since else None,
            "until": f.until.isoformat() if f.until else None,
            "region_boost": self.region,
            "instrument_boost": self.instruments,
            "time_sensitive": self.time_sensitive,
            "notes": self.notes,
        }


def _month_range(name: str, year: str | None, now: datetime) -> tuple[datetime, datetime]:
    month = list(calendar.month_name).index(name.capitalize())
    y = int(year) if year else (now.year if month <= now.month else now.year - 1)
    start = datetime(y, month, 1, tzinfo=UTC)
    end = datetime(y + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def parse_time(question: str, now: datetime) -> tuple[datetime | None, datetime | None, str | None]:
    if m := _LAST_N.search(question):
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"hour": timedelta(hours=n), "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=31 * n)}[unit]
        return now - delta, None, m.group(0)
    for pattern, delta in _RELATIVE:
        if m := pattern.search(question):
            return now - delta, None, m.group(0)
    if m := _MONTH.search(question):
        # "May" is also a verb, so a bare "May" needs a year; other months need a capital letter.
        name, year = m.group(1), m.group(2)
        if year or (name[0].isupper() and name.lower() != "may"):
            # A month names when something *happened*; minutes and accounts of a September
            # meeting are published weeks later. So bound the start only, never the end.
            start, _ = _month_range(name, year, now)
            return start, None, m.group(0)
    return None, None, None


def plan_query(question: str, now: datetime | None = None) -> QueryPlan:
    now = now or datetime.now(UTC)
    question = question.strip()
    expansions = list(dict.fromkeys(
        GLOSSARY[a] for a in _GLOSSARY_RE.findall(question) if GLOSSARY[a].lower() not in question.lower()
    ))
    plan = QueryPlan(question=question,
                     search_text=f"{question} ({'; '.join(expansions)})" if expansions else question)
    if expansions:
        plan.notes.append(f"expanded acronyms: {expansions}")

    markets = sorted(m.value for m in tag_markets(question))
    if markets:
        plan.filters.markets = markets
        plan.notes.append(f"market filter {markets}")

    since, until, phrase = parse_time(question, now)
    if since:
        plan.filters.since, plan.filters.until = since, until
        plan.notes.append(f"date filter from '{phrase}'")

    if _PK_TERMS.search(question):
        plan.region = "pk"
    plan.instruments = extract_instruments(question)
    plan.time_sensitive = bool(_TIME_SENSITIVE.search(question))
    return plan
