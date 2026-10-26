from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from app.database import Database
from app.market_repository import MarketRepository
from app.providers.prices import UnsupportedSymbolError
from app.services.market import MarketService
from fakes import FakeHistory, listing, synthetic_bars


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _service(tmp_path: Path, series: dict | None = None) -> tuple[MarketService, FakeHistory, Clock]:
    history = FakeHistory(
        series
        or {
            "ACME": {"meta": listing("Acme Corporation"), "bars": synthetic_bars(600, step=0.5)},
            "SPY": {
                "meta": listing("SPDR S&P 500 ETF", instrument_type="ETF"),
                "bars": synthetic_bars(600, step=0.1),
            },
            "BRK-B": {"meta": listing("Berkshire Hathaway Inc."), "bars": synthetic_bars(30)},
            "RY": {"meta": listing("Royal Bank of Canada", currency="CAD"), "bars": synthetic_bars(30)},
            "VFIAX": {
                "meta": listing("Vanguard 500 Index Admiral", instrument_type="MUTUALFUND"),
                "bars": synthetic_bars(30),
            },
            "^VIX": {
                "meta": listing("CBOE Volatility Index", instrument_type="INDEX"),
                "bars": synthetic_bars(5, base=18),
            },
        }
    )
    clock = Clock()
    service = MarketService(
        MarketRepository(Database(tmp_path / "market.sqlite3")), provider=history, clock=clock
    )
    return service, history, clock


def test_history_is_cached_then_refreshed_incrementally(tmp_path: Path) -> None:
    service, history, clock = _service(tmp_path)
    meta, bars, stale = service.ensure_history("acme")
    assert (meta["symbol"], meta["asset_type"], len(bars), stale) == ("ACME", "STOCK", 600, False)
    assert history.calls == [("ACME", "10y")]

    clock.now += timedelta(minutes=10)
    service.ensure_history("ACME")
    assert history.calls == [("ACME", "10y")]

    clock.now += timedelta(minutes=10)
    _, bars, _ = service.ensure_history("ACME")
    assert history.calls[-1] == ("ACME", "1mo")
    assert len(bars) == 600

    clock.now += timedelta(minutes=20)
    history.offline = True
    _, bars, stale = service.ensure_history("ACME")
    assert stale is True
    assert len(bars) == 600


def test_class_shares_use_provider_spelling_and_unsupported_listings_are_rejected(tmp_path: Path) -> None:
    service, history, _ = _service(tmp_path)
    meta, _, _ = service.ensure_history("brk-b")
    assert meta["symbol"] == "BRK.B"
    assert history.calls[-1] == ("BRK-B", "10y")
    with pytest.raises(UnsupportedSymbolError, match="only USD listings"):
        service.ensure_history("RY")
    with pytest.raises(UnsupportedSymbolError, match="not a stock or ETF"):
        service.ensure_history("VFIAX")
    with pytest.raises(UnsupportedSymbolError):
        service.ensure_history("XIC.TO")
    history.offline = True
    with pytest.raises(RuntimeError):
        service.ensure_history("NEW")
    assert service.repository.symbol("RY") is None


def test_chart_slices_range_with_warmed_up_indicators(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    chart = service.chart("ACME", "3M")
    last = date.fromisoformat(chart["bars"][-1]["date"])
    assert date.fromisoformat(chart["bars"][0]["date"]) >= last - timedelta(days=92)
    assert all(len(values) == len(chart["bars"]) for values in chart["indicators"].values())

    year = service.chart("ACME", "1Y")
    assert year["indicators"]["sma200"][0] is not None
    assert year["quote"] == {
        "last": 399.5,
        "change": 0.5,
        "change_pct": 0.001253,
        "as_of": year["bars"][-1]["date"],
    }
    assert len(service.chart("ACME", "MAX")["bars"]) == 600
    with pytest.raises(ValueError, match="Unsupported range"):
        service.chart("ACME", "2W")


def test_technical_setup_describes_trend_momentum_and_relative_strength(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    setup = service.technicals("ACME")
    assert setup["trend"]["label"] == "Uptrend"
    assert setup["trend"]["above_sma50"] is True
    assert setup["rsi14"] == 100.0
    assert setup["rsi_zone"] == "overbought"
    assert setup["macd"]["state"] in {"bullish", "bearish"}
    assert setup["range_52w"]["high"] == 400.5
    assert 0.99 < setup["range_52w"]["position"] < 1
    assert setup["atr14"] == pytest.approx(2.0)
    assert setup["atr_stop"] == pytest.approx(399.5 - 4.0)
    assert setup["volume_ratio"] == 1.0
    strength = setup["relative_strength_3m"]
    assert strength["benchmark"] == "SPY"
    assert strength["difference"] == pytest.approx(
        strength["symbol_return"] - strength["benchmark_return"], abs=1e-5
    )
    assert strength["difference"] > 0


def test_watchlist_add_list_and_remove(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    assert service.add_to_watchlist("acme") == "ACME"
    service.add_to_watchlist("SPY")
    service.add_to_watchlist("ACME")
    items = service.watchlist()["items"]
    assert [item["symbol"] for item in items] == ["ACME", "SPY"]
    assert items[0]["change"] == 0.5
    assert items[1]["asset_type"] == "ETF"
    with pytest.raises(UnsupportedSymbolError):
        service.add_to_watchlist("RY")
    service.remove_from_watchlist("acme")
    assert [item["symbol"] for item in service.watchlist()["items"]] == ["SPY"]
    with pytest.raises(KeyError):
        service.remove_from_watchlist("ACME")


def test_market_strip_is_cached_and_tolerates_missing_symbols(tmp_path: Path) -> None:
    service, history, clock = _service(tmp_path)
    strip = service.market_strip()
    by_label = {item["label"]: item for item in strip["items"]}
    assert by_label["SPY"]["last"] is not None
    assert by_label["VIX"]["last"] == pytest.approx(20.0)
    assert by_label["Gold"]["last"] is None
    calls = len(history.calls)
    clock.now += timedelta(minutes=4)
    service.market_strip()
    assert len(history.calls) == calls
    clock.now += timedelta(minutes=2)
    service.market_strip()
    assert len(history.calls) > calls
