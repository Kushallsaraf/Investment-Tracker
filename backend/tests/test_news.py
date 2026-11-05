from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.database import Database
from app.providers.news import dedupe, parse_feed
from app.services.container import Services, build_services
from app.services.news import describe_8k
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
BARS = synthetic_bars(300)

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>Acme posts record margin</title><link>https://example.com/a</link>
  <description>&lt;p&gt;Margins &amp;amp; demand rose.&lt;/p&gt;</description>
  <pubDate>Wed, 04 Nov 2026 21:31:33 +0000</pubDate><dc:creator>Wire Service</dc:creator></item>
<item><title>Acme shares slump on guidance</title><link>https://example.com/b</link>
  <description>@media (max-width: 768px) { .x { width: 100% } }</description>
  <pubDate>Mon, 02 Nov 2026 13:00:00 +0000</pubDate></item>
<item><title>No date</title><link>https://example.com/c</link></item>
<item><title>Not https</title><link>http://example.com/d</link>
  <pubDate>Mon, 02 Nov 2026 13:00:00 +0000</pubDate></item>
</channel></rss>"""


class FakeNews:
    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items = items if items is not None else parse_feed(RSS, "Yahoo Finance")
        self.calls = 0
        self.offline = False

    def headlines(self, symbol: str) -> dict[str, Any]:
        self.calls += 1
        if self.offline:
            raise ConnectionError("No news feed could be reached")
        return {"items": self.items, "failures": {}, "fetched_at": NOW.isoformat()}


class FakeScorer:
    model = "fake-finbert"

    def __init__(self) -> None:
        self.scored: list[str] = []

    def score(self, texts: list[str]) -> list[dict[str, float]]:
        self.scored.extend(texts)
        return [
            {"positive": 0.9, "neutral": 0.05, "negative": 0.05}
            if "record" in text
            else {"positive": 0.1, "neutral": 0.1, "negative": 0.8}
            for text in texts
        ]


class FilingSec(FakeSec):
    def __init__(self) -> None:
        super().__init__()
        recent = self.submissions_by_cik[1234]["filings"]["recent"]
        recent["form"] = ["8-K", "4", "8-K", "10-Q"]
        recent["filingDate"] = ["2026-11-04", "2026-11-01", "2026-08-01", "2026-08-05"]
        recent["accessionNumber"] = ["0001-26-000100", "0001-26-000099", "0001-26-000050", "0001-26-000051"]
        recent["primaryDocument"] = ["ex99.htm", "form4.xml", "old.htm", "q.htm"]
        recent["items"] = ["2.02,9.01", "", "5.02", ""]


def _services(
    tmp_path: Path, *, scorer: Any = None, news: FakeNews | None = None, sec: Any = None
) -> Services:
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": BARS},
            "VOO": {"meta": listing("Vanguard S&P 500 ETF", instrument_type="ETF"), "bars": BARS},
        }
    )
    services = build_services(
        Database(tmp_path / "news.sqlite3"),
        history=history,
        prices=FakePrices(),
        sec_client=sec or FilingSec(),
        news=news or FakeNews(),
        scorer=scorer,
    )
    services.news.clock = lambda: NOW
    return services


def test_feeds_are_cleaned_and_merged() -> None:
    items = parse_feed(RSS, "Nasdaq")
    assert [item["title"] for item in items] == ["Acme posts record margin", "Acme shares slump on guidance"]
    first, second = items
    assert first["summary"] == "Margins & demand rose."
    assert (first["publisher"], first["feed"]) == ("Wire Service", "Nasdaq")
    assert first["published_at"] == "2026-11-04T21:31:33+00:00"
    assert second["summary"] is None  # page CSS instead of prose
    copy = {**first, "url": "https://example.com/elsewhere", "published_at": "2026-11-04T22:00:00+00:00"}
    assert [item["url"] for item in dedupe([copy, *items])] == ["https://example.com/a", "https://example.com/b"]


def test_8k_items_are_described() -> None:
    assert describe_8k("2.02,9.01") == "Earnings results"
    assert describe_8k("5.02, 7.01") == "Director or officer change; Regulation FD disclosure"
    assert describe_8k("9.01") == "Current report"
    assert describe_8k("6.05") == "Item 6.05"


def test_headlines_are_scored_once_and_trended(tmp_path: Path) -> None:
    scorer = FakeScorer()
    news = FakeNews()
    services = _services(tmp_path, scorer=scorer, news=news)
    result = services.news.news("acme")
    assert result["symbol"] == "ACME"
    titles = [row["title"] for row in result["headlines"]]
    assert titles == ["Acme posts record margin", "Acme shares slump on guidance"]
    top = result["headlines"][0]["sentiment"]
    assert (top["label"], top["net"], top["model"]) == ("positive", 0.85, "fake-finbert")

    sentiment = result["sentiment"]
    assert sentiment["available"] is True
    assert sentiment["counts"] == {"positive": 1, "neutral": 0, "negative": 1}
    assert sentiment["net"] == pytest.approx((0.85 - 0.7) / 2, abs=0.001)
    trend = {day["date"]: day for day in sentiment["trend"]}
    assert len(trend) == 7
    assert trend["2026-11-04"] == {"date": "2026-11-04", "count": 1, "net": 0.85}
    assert trend["2026-11-05"]["net"] is None

    filings = result["filings"]
    assert [row["title"] for row in filings] == ["8-K: Earnings results"]
    assert filings[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1234/000126000100/ex99.htm"
    assert filings[0]["sentiment"] is None

    # Within 30 minutes the cache answers; scores are never recomputed.
    services.news.news("ACME")
    assert news.calls == 1
    services.news.clock = lambda: NOW + timedelta(minutes=31)
    services.news.news("ACME")
    assert news.calls == 2
    assert len(scorer.scored) == 2


def test_missing_sentiment_and_outages_are_explicit(tmp_path: Path) -> None:
    news = FakeNews()
    services = _services(tmp_path, scorer=None, news=news)
    result = services.news.news("ACME")
    assert result["headlines"][0]["sentiment"] is None
    assert result["sentiment"]["available"] is False
    assert "not installed" in result["sentiment"]["reason"]

    news.offline = True
    services.news.clock = lambda: NOW + timedelta(hours=1)
    offline = services.news.news("ACME")
    assert offline["stale"] is True
    assert len(offline["headlines"]) == 2  # the saved copy is still shown
    assert any("No news feed" in warning for warning in offline["warnings"])


def test_etfs_skip_sec_filings(tmp_path: Path) -> None:
    sec = FilingSec()
    services = _services(tmp_path, sec=sec, news=FakeNews([]))
    result = services.news.news("VOO")
    assert result["filings"] == []
    assert result["sources"] == ["Yahoo Finance RSS", "Nasdaq RSS"]
    assert result["sentiment"]["available"] is False
    assert result["sentiment"]["reason"] == "No headlines in the last 7 days"
