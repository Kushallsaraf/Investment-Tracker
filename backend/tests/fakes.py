"""Synthetic, network-free test doubles shared by the backend tests."""

from __future__ import annotations

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
