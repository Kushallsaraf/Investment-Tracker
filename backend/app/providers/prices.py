"""Pluggable latest-price provider with a conservative Yahoo daily adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import quote

import httpx


class PriceProvider(Protocol):
    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]: ...


class YahooDailyPriceProvider:
    """Fetch the latest daily observation; never labels it real-time."""

    source = "Yahoo Finance chart"
    supports_automatic_refresh = False
    automatic_refresh_seconds: int | None = None

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Portfolio-Manager/0.2 (+local read-only dashboard)"},
        )

    @staticmethod
    def provider_symbol(canonical_symbol: str) -> str:
        # TSX uses dots for a single class suffix (for example HPS.A), while
        # Yahoo represents the same suffix with a hyphen (HPS-A.TO). Keep the
        # canonical exchange symbol in SQLite and translate only at this boundary.
        for exchange_suffix in (".TO", ".V"):
            if canonical_symbol.endswith(exchange_suffix):
                base = canonical_symbol[: -len(exchange_suffix)]
                if base.count(".") == 1:
                    return f"{base.replace('.', '-')}{exchange_suffix}"
        return canonical_symbol

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        symbol = self.provider_symbol(str(instrument["canonical_symbol"]))
        endpoint = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='.-')}"
        response = self.client.get(endpoint, params={"range": "5d", "interval": "1d"})
        response.raise_for_status()
        payload = response.json()
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart["error"].get("description") or "Price lookup failed"))
        results = chart.get("result") or []
        if not results:
            raise RuntimeError("Price provider returned no result")
        result = results[0]
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
        currency = str(meta.get("currency") or instrument["trading_currency"]).upper()
        if currency not in {"CAD", "USD"}:
            raise RuntimeError(f"Unsupported quote currency: {currency}")
        quote_status = "delayed" if delay > 0 else "real_time" if market_state == "REGULAR" else "end_of_day"
        return {
            "price": format(price, "f"),
            "currency": currency,
            "observed_at": observed.isoformat(),
            "fetched_at": fetched.isoformat(),
            "source": self.source,
            "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='.-')}",
            "quote_status": quote_status,
            "delay_minutes": delay or None,
            "stale": observed < fetched - timedelta(days=5),
        }
