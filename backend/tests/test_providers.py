from __future__ import annotations

import httpx
from app.providers.fx import BankOfCanadaFxProvider
from app.providers.prices import YahooDailyPriceProvider


def test_yahoo_adapter_translates_single_tsx_class_suffix() -> None:
    assert YahooDailyPriceProvider.provider_symbol("HPS.A.TO") == "HPS-A.TO"
    assert YahooDailyPriceProvider.provider_symbol("BBD.B.TO") == "BBD-B.TO"
    assert YahooDailyPriceProvider.provider_symbol("XIC.TO") == "XIC.TO"
    assert YahooDailyPriceProvider.provider_symbol("BRK.B") == "BRK.B"


def test_yahoo_adapter_returns_timestamped_eod_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chart": {
                    "error": None,
                    "result": [
                        {
                            "meta": {
                                "currency": "CAD",
                                "regularMarketPrice": 42.5,
                                "regularMarketTime": 1788566400,
                                "exchangeDataDelayedBy": 0,
                            },
                            "timestamp": [1788566400],
                            "indicators": {"quote": [{"close": [42.5]}]},
                        }
                    ],
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = YahooDailyPriceProvider(client)
    quote = provider.quote({"canonical_symbol": "XIC.TO", "trading_currency": "CAD"})
    assert quote["price"] == "42.5"
    assert quote["quote_status"] == "end_of_day"
    assert quote["observed_at"]


def test_yahoo_adapter_labels_open_market_quote_real_time() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chart": {
                    "error": None,
                    "result": [
                        {
                            "meta": {
                                "currency": "CAD",
                                "regularMarketPrice": 42.5,
                                "regularMarketTime": 1788566400,
                                "exchangeDataDelayedBy": 0,
                                "marketState": "REGULAR",
                            },
                            "timestamp": [1788566400],
                            "indicators": {"quote": [{"close": [42.5]}]},
                        }
                    ],
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    quote = YahooDailyPriceProvider(client).quote({"canonical_symbol": "XIC.TO", "trading_currency": "CAD"})
    assert quote["quote_status"] == "real_time"


def test_yahoo_adapter_prioritizes_reported_delay() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chart": {
                    "error": None,
                    "result": [
                        {
                            "meta": {
                                "currency": "CAD",
                                "regularMarketPrice": 42.5,
                                "regularMarketTime": 1788566400,
                                "exchangeDataDelayedBy": 15,
                                "marketState": "REGULAR",
                            },
                            "timestamp": [1788566400],
                            "indicators": {"quote": [{"close": [42.5]}]},
                        }
                    ],
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    quote = YahooDailyPriceProvider(client).quote({"canonical_symbol": "XIC.TO", "trading_currency": "CAD"})
    assert quote["quote_status"] == "delayed"
    assert quote["delay_minutes"] == 15


def test_bank_of_canada_adapter_selects_latest_valid_observation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"d": "2026-09-03", "FXUSDCAD": {"v": "1.3700"}},
                    {"d": "2026-09-04", "FXUSDCAD": {"v": "1.3750"}},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rate = BankOfCanadaFxProvider(client).usd_cad()
    assert rate["rate"] == "1.3750"
    assert rate["base_currency"] == "USD"
