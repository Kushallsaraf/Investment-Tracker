"""Daily OHLCV history from Yahoo's free chart endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.providers.prices import UnsupportedSymbolError

HISTORY_SOURCE = "Yahoo Finance chart (daily)"


def _at(values: list[Any] | None, index: int) -> Any:
    return values[index] if values and index < len(values) else None


class HistoryProvider(Protocol):
    def daily_bars(self, provider_symbol: str, period: str) -> dict[str, Any]: ...


class YahooHistoryProvider:
    """Return dated daily bars plus the listing metadata Yahoo reports with them."""

    source = HISTORY_SOURCE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Portfolio-Manager/0.5 (+local research dashboard)"},
        )

    def daily_bars(self, provider_symbol: str, period: str) -> dict[str, Any]:
        endpoint = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(provider_symbol, safe='-^=.')}"
        response = self.client.get(
            endpoint, params={"range": period, "interval": "1d", "events": "div,splits"}
        )
        if response.status_code == 404:
            raise UnsupportedSymbolError(f"{provider_symbol} was not found")
        response.raise_for_status()
        chart = response.json().get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart["error"].get("description") or "History lookup failed"))
        results = chart.get("result") or []
        if not results:
            raise RuntimeError("History provider returned no result")
        result = results[0]
        meta = result.get("meta") or {}
        # Daily bars are stamped at the session open in UTC; shift to exchange time for the date.
        offset = timedelta(seconds=int(meta.get("gmtoffset") or 0))
        indicators = result.get("indicators") or {}
        quote_rows = (indicators.get("quote") or [{}])[0]
        adjusted = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
        bars: list[dict[str, Any]] = []
        for index, stamp in enumerate(result.get("timestamp") or []):
            values = [_at(quote_rows.get(field), index) for field in ("open", "high", "low", "close")]
            if any(value is None for value in values):
                continue
            volume = _at(quote_rows.get("volume"), index)
            adj_close = _at(adjusted, index)
            bars.append(
                {
                    "date": (datetime.fromtimestamp(int(stamp), tz=UTC) + offset).date().isoformat(),
                    "open": float(values[0]),
                    "high": float(values[1]),
                    "low": float(values[2]),
                    "close": float(values[3]),
                    "adj_close": float(adj_close) if adj_close is not None else float(values[3]),
                    "volume": int(volume) if volume is not None else None,
                }
            )
        # A session can be reported twice (in-progress bar plus regular close); keep the latest.
        deduplicated = {bar["date"]: bar for bar in bars}
        return {
            "meta": {
                "currency": str(meta.get("currency") or "").upper(),
                "instrument_type": str(meta.get("instrumentType") or "").upper(),
                "name": str(meta.get("longName") or meta.get("shortName") or provider_symbol),
                "exchange": str(meta.get("fullExchangeName") or meta.get("exchangeName") or ""),
                "market_price": meta.get("regularMarketPrice"),
                "market_time": meta.get("regularMarketTime"),
            },
            "bars": [deduplicated[key] for key in sorted(deduplicated)],
        }
