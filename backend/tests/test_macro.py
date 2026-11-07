from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.database import Database
from app.providers.fred import FredClient, FredNotConfiguredError, parse_fomc_calendar
from app.services.container import Services, build_services
from app.services.macro import INDICATORS, MACRO_KEY, summarize, themes_for
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars

NOW = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)

FOMC_PAGE = """
<h4><a>2026 FOMC Meetings</a></h4>
<div class="fomc-meeting__month"><strong>October</strong></div><div class="fomc-meeting__date">27-28</div>
<div class="fomc-meeting__month"><strong>December</strong></div><div class="fomc-meeting__date">8-9*</div>
<div class="fomc-meeting__month"><strong>Dec/Jan</strong></div><div class="fomc-meeting__date">31-1</div>
<div class="fomc-meeting__month"><strong>June</strong></div>
<div class="fomc-meeting__date">(notation vote)</div>
<h4><a>2027 FOMC Meetings</a></h4>
<div class="fomc-meeting__month"><strong>January</strong></div><div class="fomc-meeting__date">26-27</div>
"""


def monthly(start: str, values: list[float]) -> list[tuple[str, float]]:
    year, month = int(start[:4]), int(start[5:7])
    rows = []
    for value in values:
        rows.append((date(year, month, 1).isoformat(), value))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return rows


class FakeFred:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.offline = False

    def observations(self, series_id: str, start: date) -> list[tuple[str, float]]:
        self.calls.append(series_id)
        if self.offline:
            raise RuntimeError("FRED could not be reached (ConnectError)")
        if series_id == "CPIAUCSL":
            return monthly("2025-01-01", [300 + index for index in range(21)])
        if series_id == "PAYEMS":
            return monthly("2026-07-01", [159_000, 159_060, 159_225])
        if series_id == "DGS10":
            days = [(NOW.date() - timedelta(days=offset)).isoformat() for offset in range(40, 0, -1)]
            return [(day, 4.0 + index * 0.01) for index, day in enumerate(days)]
        if series_id == "ICSA":
            return [("2026-10-24", 195_000), ("2026-10-31", 189_000)]
        return monthly("2026-08-01", [4.2, 4.1])

    def release_dates(self, release_id: int, start: date) -> list[str]:
        self.calls.append(f"release:{release_id}")
        if release_id == 50:
            return ["2026-11-06", "2026-12-04", "2027-01-08"]
        if release_id == 180:
            return ["2026-11-12", "2026-11-19", "2026-11-26"]
        return []


class FakeFed:
    def fomc_meetings(self) -> list[dict[str, Any]]:
        return parse_fomc_calendar(FOMC_PAGE)


class FakeMacroNews:
    def headlines(self, symbol: str = "") -> dict[str, Any]:
        def item(title: str, hours: int) -> dict[str, Any]:
            published = (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")
            return {
                "title": title,
                "summary": None,
                "url": f"https://example.com/{hours}",
                "publisher": "CNBC",
                "published_at": published,
                "feed": "CNBC World",
            }

        return {
            "items": [
                item("Oil jumps as Iran conflict threatens supply", 2),
                item("Fed's Powell signals patience on rate cuts", 5),
                item("I'm 66 with $900,000 saved. Can I retire?", 6),
            ],
            "failures": {},
        }


class FakeScorer:
    model = "fake"

    def score(self, texts: list[str]) -> list[dict[str, float]]:
        return [{"positive": 0.1, "neutral": 0.2, "negative": 0.7} for _ in texts]


def _services(tmp_path: Path, fred: Any = None) -> Services:
    services = build_services(
        Database(tmp_path / "macro.sqlite3"),
        history=FakeHistory({"ACME": {"meta": listing("Acme Corporation"), "bars": synthetic_bars(300)}}),
        prices=FakePrices(),
        sec_client=FakeSec(),
        news=None,
        scorer=FakeScorer(),
        fred=fred or FakeFred(),
        fed_calendar=FakeFed(),
        macro_news=FakeMacroNews(),
    )
    services.macro.clock = lambda: NOW
    return services


def test_fomc_calendar_parsing_handles_projections_and_year_ends() -> None:
    meetings = parse_fomc_calendar(FOMC_PAGE)
    assert meetings == [
        {"start": "2026-10-27", "end": "2026-10-28", "projections": False},
        {"start": "2026-12-08", "end": "2026-12-09", "projections": True},
        {"start": "2026-12-31", "end": "2027-01-01", "projections": False},
        {"start": "2027-01-26", "end": "2027-01-27", "projections": False},
    ]


def test_indicator_transforms() -> None:
    by_key = {indicator.key: indicator for indicator in INDICATORS}
    cpi = summarize(by_key["cpi"], FakeFred().observations("CPIAUCSL", date(2024, 1, 1)))
    assert (cpi["value"], cpi["as_of"]) == (round((320 / 308 - 1) * 100, 2), "2026-09-01")
    assert cpi["previous_as_of"] == "2026-08-01"
    payrolls = summarize(by_key["payrolls"], FakeFred().observations("PAYEMS", date(2024, 1, 1)))
    assert (payrolls["value"], payrolls["previous"]) == (165.0, 60.0)
    claims = summarize(by_key["claims"], FakeFred().observations("ICSA", date(2024, 1, 1)))
    assert (claims["value"], claims["unit"]) == (189.0, "K")
    ten_year = summarize(by_key["ten_year"], FakeFred().observations("DGS10", date(2024, 1, 1)))
    assert ten_year["compared_with"] == "about a month earlier"
    assert ten_year["previous_as_of"] <= (NOW.date() - timedelta(days=31)).isoformat()
    assert summarize(by_key["gdp"], [])["available"] is False


def test_themes_are_matched_by_keywords() -> None:
    assert themes_for("Oil jumps as Iran conflict threatens supply") == ["geopolitics", "energy"]
    assert themes_for("Fed's Powell signals patience on rate cuts") == ["rates"]
    assert themes_for("I'm 66 with $900,000 saved. Can I retire?") == []


def test_snapshot_combines_data_calendar_and_themed_news(tmp_path: Path) -> None:
    services = _services(tmp_path)
    services.portfolio.upsert_position(
        symbol="ACME", quantity="1", average_cost="90", account_name="Brokerage"
    )
    acme = services.portfolio_repository.instrument_by_symbol("ACME")
    services.portfolio_repository.update_instrument_sector(acme["id"], "Energy")

    snapshot = services.macro.snapshot()
    assert snapshot["fred_configured"] is True
    unemployment = next(row for row in snapshot["indicators"]["items"] if row["key"] == "unemployment")
    latest = (unemployment["value"], unemployment["previous"], unemployment["as_of"])
    assert latest == (4.1, 4.2, "2026-09-01")

    events = snapshot["calendar"]["events"]
    assert [(row["date"], row["name"]) for row in events] == [
        ("2026-11-06", "Jobs report"),
        ("2026-11-12", "Weekly jobless claims"),
        ("2026-12-04", "Jobs report"),
        ("2026-12-09", "Fed rate decision (FOMC)"),
    ]
    assert events[3]["detail"] == "Rate decision with economic projections"

    news = snapshot["news"]
    assert [row["title"] for row in news["headlines"]] == [
        "Oil jumps as Iran conflict threatens supply",
        "Fed's Powell signals patience on rate cuts",
    ]
    energy = next(row for row in news["themes"] if row["key"] == "energy")
    assert (energy["count"], energy["net"]) == (1, -0.6)
    assert [holding["symbol"] for holding in energy["holdings"]] == ["ACME"]
    assert energy["holdings_weight"] == 1.0
    assert news["themes"][0]["count"] >= news["themes"][-1]["count"]


def test_series_are_cached_and_stale_copies_survive_outages(tmp_path: Path) -> None:
    fred = FakeFred()
    services = _services(tmp_path, fred)
    services.macro.indicators()
    calls = len(fred.calls)
    services.macro.indicators()
    assert len(fred.calls) == calls

    fred.offline = True
    services.macro.clock = lambda: NOW + timedelta(hours=7)
    later = services.macro.indicators()["items"]
    assert all(row["stale"] for row in later)
    assert next(row for row in later if row["key"] == "unemployment")["value"] == 4.1


def test_missing_fred_key_still_shows_news_and_fed_meetings(tmp_path: Path) -> None:
    services = _services(tmp_path, FredClient(None))
    snapshot = services.macro.snapshot()
    assert snapshot["fred_configured"] is False
    assert "FRED_API_KEY" in snapshot["indicators"]["unavailable"]
    assert [row["name"] for row in snapshot["calendar"]["events"]] == ["Fed rate decision (FOMC)"]
    assert snapshot["calendar"]["unavailable"]
    assert len(snapshot["news"]["headlines"]) == 2
    assert services.news.repository.last_fetch(MACRO_KEY) is not None
    with pytest.raises(FredNotConfiguredError):
        FredClient(None).observations("UNRATE", date(2026, 1, 1))
