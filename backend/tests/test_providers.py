from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.providers.prices import UnsupportedSymbolError, YahooDailyPriceProvider, normalize_symbol


def _chart(meta: dict[str, Any]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chart": {
                    "error": None,
                    "result": [
                        {
                            "meta": {
                                "currency": "USD",
                                "regularMarketPrice": 42.5,
                                "regularMarketTime": 1788566400,
                                "exchangeDataDelayedBy": 0,
                                **meta,
                            },
                            "timestamp": [1788566400],
                            "indicators": {"quote": [{"close": [42.5]}]},
                        }
                    ],
                }
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_us_symbols_are_normalized_and_foreign_suffixes_rejected() -> None:
    assert normalize_symbol(" aapl ") == "AAPL"
    assert normalize_symbol("brk-b") == "BRK.B"
    assert normalize_symbol("BRK/B") == "BRK.B"
    for unsupported in ("XIC.TO", "RY.TO", "", "TOOLONGX", "1ABC"):
        with pytest.raises(UnsupportedSymbolError):
            normalize_symbol(unsupported)


def test_yahoo_adapter_translates_class_share_dot_to_hyphen() -> None:
    assert YahooDailyPriceProvider.provider_symbol("BRK.B") == "BRK-B"
    assert YahooDailyPriceProvider.provider_symbol("AAPL") == "AAPL"


def test_yahoo_adapter_returns_timestamped_eod_price() -> None:
    quote = YahooDailyPriceProvider(_chart({})).quote({"canonical_symbol": "AAPL"})
    assert quote["price"] == "42.5"
    assert quote["quote_status"] == "end_of_day"
    assert quote["observed_at"]
    assert quote["source_url"] == "https://finance.yahoo.com/quote/AAPL"


def test_yahoo_adapter_labels_open_market_quote_real_time() -> None:
    quote = YahooDailyPriceProvider(_chart({"marketState": "REGULAR"})).quote({"canonical_symbol": "AAPL"})
    assert quote["quote_status"] == "real_time"


def test_yahoo_adapter_prioritizes_reported_delay() -> None:
    provider = YahooDailyPriceProvider(_chart({"exchangeDataDelayedBy": 15, "marketState": "REGULAR"}))
    quote = provider.quote({"canonical_symbol": "AAPL"})
    assert quote["quote_status"] == "delayed"
    assert quote["delay_minutes"] == 15


def test_yahoo_adapter_rejects_non_usd_listings() -> None:
    provider = YahooDailyPriceProvider(_chart({"currency": "CAD"}))
    with pytest.raises(UnsupportedSymbolError, match="only USD listings"):
        provider.quote({"canonical_symbol": "AAPL"})


def test_yahoo_lookup_maps_instrument_identity() -> None:
    provider = YahooDailyPriceProvider(
        _chart({"instrumentType": "ETF", "longName": "Vanguard S&P 500 ETF", "fullExchangeName": "NYSEArca"})
    )
    assert provider.lookup("voo") == {
        "canonical_symbol": "VOO",
        "security_name": "Vanguard S&P 500 ETF",
        "asset_type": "ETF",
        "exchange": "NYSEArca",
    }
    with pytest.raises(UnsupportedSymbolError, match="not a stock or ETF"):
        YahooDailyPriceProvider(_chart({"instrumentType": "MUTUALFUND"})).lookup("VFIAX")
