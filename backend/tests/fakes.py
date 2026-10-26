"""Synthetic, network-free test doubles shared by the backend tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.providers.prices import UnsupportedSymbolError, normalize_symbol

OBSERVED_AT = "2026-09-11T20:00:00+00:00"
FETCHED_AT = "2026-09-11T20:01:00+00:00"

IDENTITIES: dict[str, dict[str, str]] = {
    "ACME": {"security_name": "Acme Corporation", "asset_type": "STOCK", "exchange": "NYSE"},
    "SYNE": {"security_name": "Synthetic Equity ETF", "asset_type": "ETF", "exchange": "NYSEArca"},
    "BRK.B": {"security_name": "Berkshire Hathaway Inc.", "asset_type": "STOCK", "exchange": "NYSE"},
}


class FakePrices:
    """Return fixed USD prices and identities; unknown symbols are rejected like a non-US listing."""

    source = "Synthetic quote"
    supports_automatic_refresh = False
    automatic_refresh_seconds = None

    def __init__(self, prices: dict[str, str] | None = None, *, stale: bool = False) -> None:
        self.prices = prices or {"ACME": "120", "SYNE": "50", "BRK.B": "400"}
        self.stale = stale
        self.lookups: list[str] = []

    def lookup(self, symbol: str) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        self.lookups.append(canonical)
        if canonical not in IDENTITIES:
            raise UnsupportedSymbolError(f"{canonical} was not found")
        return {"canonical_symbol": canonical, **IDENTITIES[canonical]}

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        return {
            "price": self.prices[instrument["canonical_symbol"]],
            "observed_at": OBSERVED_AT,
            "fetched_at": FETCHED_AT,
            "source": self.source,
            "source_url": "https://example.invalid/synthetic",
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": self.stale,
        }


def synthetic_bars(count: int, *, base: float = 100.0, step: float = 0.5) -> list[dict[str, Any]]:
    """Weekday bars rising by `step` each session, with a fixed 2-point high-low range."""
    bars: list[dict[str, Any]] = []
    day = date(2023, 1, 2)
    while len(bars) < count:
        if day.weekday() < 5:
            close = base + step * len(bars)
            bars.append(
                {
                    "date": day.isoformat(),
                    "open": close - 0.2,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "adj_close": close,
                    "volume": 1_000,
                }
            )
        day += timedelta(days=1)
    return bars


def listing(name: str, *, currency: str = "USD", instrument_type: str = "EQUITY") -> dict[str, Any]:
    return {
        "currency": currency,
        "instrument_type": instrument_type,
        "name": name,
        "exchange": "NYSE",
        "market_price": None,
        "market_time": None,
    }


class FakeHistory:
    """Serve full history for the initial period and only recent bars for incremental refreshes."""

    def __init__(self, series: dict[str, dict[str, Any]]) -> None:
        self.series = series
        self.calls: list[tuple[str, str]] = []
        self.offline = False

    def daily_bars(self, provider_symbol: str, period: str) -> dict[str, Any]:
        self.calls.append((provider_symbol, period))
        if self.offline:
            raise RuntimeError("synthetic outage")
        if provider_symbol not in self.series:
            raise UnsupportedSymbolError(f"{provider_symbol} was not found")
        payload = self.series[provider_symbol]
        bars = payload["bars"] if period == "10y" else payload["bars"][-5:]
        return {"meta": payload["meta"], "bars": bars}
