"""Pluggable latest-price provider with a conservative Yahoo daily adapter (US listings only)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import quote

import httpx

US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9]{0,5}(\.[A-Z])?$")
INSTRUMENT_TYPES = {"EQUITY": "STOCK", "ETF": "ETF"}


class UnsupportedSymbolError(ValueError):
    """The symbol is not a US-listed, USD-quoted stock or ETF."""


class PriceProvider(Protocol):
    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]: ...

    def lookup(self, symbol: str) -> dict[str, Any]: ...


def normalize_symbol(value: str) -> str:
    """Return the canonical US symbol (for example BRK.B) or raise for anything else."""
    symbol = value.strip().upper().replace("-", ".").replace("/", ".")
    if not US_SYMBOL.fullmatch(symbol):
        raise UnsupportedSymbolError(f"{value!r} is not a supported US ticker")
    return symbol


class YahooDailyPriceProvider:
    """Fetch the latest daily observation; never labels it real-time."""

    source = "Yahoo Finance chart"
    supports_automatic_refresh = False
    automatic_refresh_seconds: int | None = None

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Portfolio-Manager/0.4 (+local read-only dashboard)"},
        )

    @staticmethod
    def provider_symbol(canonical_symbol: str) -> str:
        # US class shares use a dot (BRK.B); Yahoo represents the class with a hyphen (BRK-B).
        return canonical_symbol.replace(".", "-")

    def _chart(self, canonical_symbol: str) -> tuple[str, dict[str, Any]]:
        symbol = self.provider_symbol(canonical_symbol)
        endpoint = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='-')}"
        response = self.client.get(endpoint, params={"range": "5d", "interval": "1d"})
        if response.status_code == 404:
            raise UnsupportedSymbolError(f"{canonical_symbol} was not found")
        response.raise_for_status()
        chart = response.json().get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart["error"].get("description") or "Price lookup failed"))
        results = chart.get("result") or []
        if not results:
            raise RuntimeError("Price provider returned no result")
        result = results[0]
        currency = str((result.get("meta") or {}).get("currency") or "").upper()
        if currency != "USD":
            raise UnsupportedSymbolError(
                f"{canonical_symbol} is quoted in {currency or 'an unknown currency'}; "
                "only USD listings are supported"
            )
        return symbol, result

    def lookup(self, symbol: str) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        _, result = self._chart(canonical)
        meta = result.get("meta") or {}
        asset_type = INSTRUMENT_TYPES.get(str(meta.get("instrumentType") or "").upper())
        if asset_type is None:
            raise UnsupportedSymbolError(f"{canonical} is not a stock or ETF")
        return {
            "canonical_symbol": canonical,
            "security_name": str(meta.get("longName") or meta.get("shortName") or canonical),
            "asset_type": asset_type,
            "exchange": str(meta.get("fullExchangeName") or meta.get("exchangeName") or "US"),
        }

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        symbol, result = self._chart(str(instrument["canonical_symbol"]))
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        observations = [
            (timestamp, close)
            for timestamp, close in zip(timestamps, closes, strict=False)
            if close is not None
        ]
        market_price = meta.get("regularMarketPrice")
        market_time = meta.get("regularMarketTime")
        if market_price is None and observations:
            market_time, market_price = observations[-1]
        if market_price is None or market_time is None:
            raise RuntimeError("Price provider returned no dated close")
        price = Decimal(str(market_price))
        if not price.is_finite() or price <= 0:
            raise RuntimeError("Price provider returned an invalid price")
        observed = datetime.fromtimestamp(int(market_time), tz=UTC)
        fetched = datetime.now(UTC)
        delay = int(meta.get("exchangeDataDelayedBy") or 0)
        market_state = str(meta.get("marketState") or "").upper()
        quote_status = "delayed" if delay > 0 else "real_time" if market_state == "REGULAR" else "end_of_day"
        return {
            "price": format(price, "f"),
            "observed_at": observed.isoformat(),
            "fetched_at": fetched.isoformat(),
            "source": self.source,
            "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='-')}",
            "quote_status": quote_status,
            "delay_minutes": delay or None,
            "stale": observed < fetched - timedelta(days=5),
        }
