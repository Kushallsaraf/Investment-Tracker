"""Cached daily history, chart payloads, technical setup, market strip, and watchlist."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.market_repository import MarketRepository
from app.providers.history import HISTORY_SOURCE, HistoryProvider, YahooHistoryProvider
from app.providers.prices import INSTRUMENT_TYPES, UnsupportedSymbolError, normalize_symbol
from app.services import indicators

REFRESH_AFTER = timedelta(minutes=15)
STRIP_REFRESH_AFTER = timedelta(minutes=5)
INITIAL_PERIOD = "10y"
INCREMENTAL_PERIOD = "1mo"
BENCHMARK = "SPY"
RANGES: dict[str, int | None] = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1827, "MAX": None}
# Bars kept ahead of the visible range so long averages (200-day) are warmed up on screen.
WARMUP_BARS = 260

MARKET_STRIP: tuple[tuple[str, str, str], ...] = (
    ("SPY", "SPY", "S&P 500 ETF"),
    ("QQQ", "QQQ", "Nasdaq-100 ETF"),
    ("DIA", "DIA", "Dow Jones ETF"),
    ("IWM", "IWM", "Russell 2000 ETF"),
    ("VIX", "^VIX", "Volatility index"),
    ("10Y", "^TNX", "10-year Treasury yield"),
    ("DXY", "DX-Y.NYB", "US dollar index"),
    ("Oil", "CL=F", "WTI crude futures"),
    ("Gold", "GC=F", "Gold futures"),
    ("BTC", "BTC-USD", "Bitcoin"),
)


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _change(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not bars:
        return {"last": None, "change": None, "change_pct": None, "as_of": None}
    last = bars[-1]["close"]
    previous = bars[-2]["close"] if len(bars) > 1 else None
    change = last - previous if previous else None
    return {
        "last": _round(last),
        "change": _round(change),
        "change_pct": _round(change / previous, 6) if change is not None and previous else None,
        "as_of": bars[-1]["date"],
    }


class MarketService:
    def __init__(
        self,
        repository: MarketRepository,
        *,
        provider: HistoryProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider or YahooHistoryProvider()
        self.clock = clock or (lambda: datetime.now(UTC))
        self._strip_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _provider_symbol(symbol: str) -> str:
        return symbol.replace(".", "-")

    def _fetch(self, symbol: str, period: str) -> None:
        payload = self.provider.daily_bars(self._provider_symbol(symbol), period)
        meta = payload["meta"]
        if meta["currency"] != "USD":
            raise UnsupportedSymbolError(
                f"{symbol} is quoted in {meta['currency'] or 'an unknown currency'}; "
                "only USD listings are supported"
            )
        asset_type = INSTRUMENT_TYPES.get(meta["instrument_type"])
        if asset_type is None:
            raise UnsupportedSymbolError(f"{symbol} is not a stock or ETF")
        if not payload["bars"]:
            raise RuntimeError(f"No daily history was returned for {symbol}")
        self.repository.save_history(
            {
                "symbol": symbol,
                "security_name": meta["name"],
                "asset_type": asset_type,
                "exchange": meta["exchange"] or "US",
            },
            payload["bars"],
            self.clock().isoformat(),
        )

    def ensure_history(self, raw_symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        """Return (symbol metadata, all cached bars, stale flag), refreshing when the cache is old."""
        symbol = normalize_symbol(raw_symbol)
        cached = self.repository.symbol(symbol)
        stale = False
        if cached is None or cached["history_fetched_at"] is None:
            self._fetch(symbol, INITIAL_PERIOD)
        elif self.clock() - datetime.fromisoformat(cached["history_fetched_at"]) > REFRESH_AFTER:
            try:
                self._fetch(symbol, INCREMENTAL_PERIOD)
            except UnsupportedSymbolError:
                raise
            except Exception:
                stale = True
        meta = self.repository.symbol(symbol)
        assert meta is not None
        return meta, self.repository.bars(symbol), stale

    def chart(self, raw_symbol: str, period: str = "1Y") -> dict[str, Any]:
        if period not in RANGES:
            raise ValueError(f"Unsupported range {period}")
        meta, bars, stale = self.ensure_history(raw_symbol)
        days = RANGES[period]
        start = 0
        if days is not None:
            cutoff = (date.fromisoformat(bars[-1]["date"]) - timedelta(days=days)).isoformat()
            start = next((index for index, bar in enumerate(bars) if bar["date"] >= cutoff), 0)
        window = bars[max(0, start - WARMUP_BARS) :]
        offset = start - max(0, start - WARMUP_BARS)
        closes = [bar["close"] for bar in window]
        upper, middle, lower = indicators.bollinger(closes)
        macd_line, macd_signal, macd_histogram = indicators.macd(closes)
        series = {
            "ema20": indicators.ema(closes, 20),
            "ema50": indicators.ema(closes, 50),
            "sma200": indicators.sma(closes, 200),
            "bb_upper": upper,
            "bb_middle": middle,
            "bb_lower": lower,
            "rsi14": indicators.rsi(closes),
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
        }
        return {
            "symbol": meta["symbol"],
            "name": meta["security_name"],
            "asset_type": meta["asset_type"],
            "exchange": meta["exchange"],
            "range": period,
            "bars": window[offset:],
            "indicators": {
                name: [_round(value) for value in values[offset:]] for name, values in series.items()
            },
            "quote": _change(bars),
            "source": HISTORY_SOURCE,
            "fetched_at": meta["history_fetched_at"],
            "stale": stale,
        }

    def technicals(self, raw_symbol: str) -> dict[str, Any]:
        meta, bars, stale = self.ensure_history(raw_symbol)
        closes = [bar["close"] for bar in bars]
        highs = [bar["high"] for bar in bars]
        lows = [bar["low"] for bar in bars]
        close = closes[-1]
        sma50 = indicators.sma(closes, 50)[-1]
        sma200 = indicators.sma(closes, 200)[-1]
        rsi14 = indicators.rsi(closes)[-1]
        atr14 = indicators.atr(highs, lows, closes)[-1]
        macd_line, macd_signal, _ = indicators.macd(closes)

        trend_label = None
        if sma50 is not None and sma200 is not None:
            if close > sma50 > sma200:
                trend_label = "Uptrend"
            elif close < sma50 < sma200:
                trend_label = "Downtrend"
            else:
                trend_label = "Mixed"

        year_ago = (date.fromisoformat(bars[-1]["date"]) - timedelta(days=365)).isoformat()
        last_year = [bar for bar in bars if bar["date"] >= year_ago]
        high_52w = max(bar["high"] for bar in last_year)
        low_52w = min(bar["low"] for bar in last_year)

        volumes = [bar["volume"] for bar in bars[-21:-1] if bar["volume"]]
        volume_ratio = (
            bars[-1]["volume"] / (sum(volumes) / len(volumes))
            if bars[-1]["volume"] and len(volumes) >= 10
            else None
        )

        return {
            "symbol": meta["symbol"],
            "as_of": bars[-1]["date"],
            "close": _round(close),
            "trend": {
                "label": trend_label,
                "sma50": _round(sma50),
                "sma200": _round(sma200),
                "above_sma50": close > sma50 if sma50 is not None else None,
                "above_sma200": close > sma200 if sma200 is not None else None,
                "distance_sma50_pct": _round(close / sma50 - 1, 6) if sma50 else None,
            },
            "rsi14": _round(rsi14, 2),
            "rsi_zone": None
            if rsi14 is None
            else "overbought" if rsi14 >= 70 else "oversold" if rsi14 <= 30 else "neutral",
            "macd": {
                "value": _round(macd_line[-1]),
                "signal": _round(macd_signal[-1]),
                "state": None
                if macd_line[-1] is None or macd_signal[-1] is None
                else "bullish" if macd_line[-1] > macd_signal[-1] else "bearish",
            },
            "range_52w": {
                "high": _round(high_52w),
                "low": _round(low_52w),
                "position": _round((close - low_52w) / (high_52w - low_52w), 6)
                if high_52w > low_52w
                else None,
            },
            "relative_strength_3m": self._relative_strength(meta["symbol"], bars),
            "atr14": _round(atr14),
            "atr_pct": _round(atr14 / close, 6) if atr14 is not None else None,
            "atr_stop": _round(close - 2 * atr14) if atr14 is not None else None,
            "volume_ratio": _round(volume_ratio, 3),
            "source": HISTORY_SOURCE,
            "stale": stale,
        }

    @staticmethod
    def _period_return(bars: list[dict[str, Any]], start_date: str) -> float | None:
        window = [bar for bar in bars if bar["date"] >= start_date]
        if len(window) < 2 or window[0]["adj_close"] <= 0:
            return None
        return window[-1]["adj_close"] / window[0]["adj_close"] - 1

    def _relative_strength(self, symbol: str, bars: list[dict[str, Any]]) -> dict[str, Any] | None:
        start = (date.fromisoformat(bars[-1]["date"]) - timedelta(days=92)).isoformat()
        own = self._period_return(bars, start)
        if own is None:
            return None
        benchmark = None
        if symbol != BENCHMARK:
            try:
                _, benchmark_bars, _ = self.ensure_history(BENCHMARK)
                benchmark = self._period_return(benchmark_bars, start)
            except Exception:
                benchmark = None
        else:
            benchmark = own
        return {
            "benchmark": BENCHMARK,
            "symbol_return": _round(own, 6),
            "benchmark_return": _round(benchmark, 6),
            "difference": _round(own - benchmark, 6) if benchmark is not None else None,
        }

    def _strip_item(self, label: str, provider_symbol: str, description: str) -> dict[str, Any]:
        try:
            bars = self.provider.daily_bars(provider_symbol, "5d")["bars"]
            return {"label": label, "symbol": provider_symbol, "description": description, **_change(bars)}
        except Exception:
            return {
                "label": label,
                "symbol": provider_symbol,
                "description": description,
                **_change([]),
            }

    def market_strip(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            if self._strip_cache is None or now - self._strip_cache[0] >= STRIP_REFRESH_AFTER:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    fresh = list(pool.map(lambda row: self._strip_item(*row), MARKET_STRIP))
                self._strip_cache = (now, fresh)
            fetched, items = self._strip_cache
        return {"items": items, "fetched_at": fetched.isoformat(), "source": HISTORY_SOURCE}

    def watchlist(self) -> dict[str, Any]:
        rows = self.repository.watchlist()

        def quote(row: dict[str, Any]) -> dict[str, Any]:
            try:
                _, bars, stale = self.ensure_history(row["symbol"])
                return {**row, **_change(bars), "stale": stale}
            except Exception:
                return {**row, **_change(self.repository.bars(row["symbol"])), "stale": True}

        with ThreadPoolExecutor(max_workers=5) as pool:
            items = list(pool.map(quote, rows))
        return {"items": items, "source": HISTORY_SOURCE}

    def add_to_watchlist(self, raw_symbol: str) -> str:
        meta, _, _ = self.ensure_history(raw_symbol)
        self.repository.add_to_watchlist(meta["symbol"])
        return str(meta["symbol"])

    def remove_from_watchlist(self, raw_symbol: str) -> None:
        self.repository.remove_from_watchlist(normalize_symbol(raw_symbol))
