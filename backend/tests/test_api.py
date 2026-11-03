from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from app.database import Database
from app.journal_repository import JournalRepository
from app.main import (
    activity_service,
    analytics_service,
    app,
    fundamentals_service,
    insider_service,
    journal_service,
    market_service,
    peer_service,
    portfolio_service,
    research_service,
    sector_service,
)
from app.market_repository import MarketRepository
from app.providers.sec import SecClient
from app.repository import PortfolioRepository
from app.sec_repository import SecRepository
from app.services.activities import ActivityService
from app.services.analytics import AnalyticsService
from app.services.fundamentals import FundamentalsService
from app.services.insiders import InsiderService
from app.services.journal import JournalService
from app.services.market import MarketService
from app.services.peers import PeerService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sec_data import SecDataService
from app.services.sectors import SectorService
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars
from fastapi.testclient import TestClient

WRITE = {"X-Portfolio-Manager": "local-ui"}
DEMO_SYMBOLS = ("AAPL", "MSFT", "NVDA", "JPM", "JNJ", "XOM", "VOO", "QQQ")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    repository = PortfolioRepository(Database(tmp_path / "api.sqlite3"))
    prices = FakePrices({"ACME": "120", "SYNE": "50", **{symbol: "100" for symbol in DEMO_SYMBOLS}})
    portfolio = PortfolioService(repository, price_provider=prices)
    sectors = SectorService(repository)
    journal_repository = JournalRepository(repository.database)
    app.dependency_overrides[portfolio_service] = lambda: portfolio
    app.dependency_overrides[sector_service] = lambda: sectors
    app.dependency_overrides[activity_service] = lambda: ActivityService(repository)
    app.dependency_overrides[analytics_service] = lambda: AnalyticsService(repository, sectors)
    app.dependency_overrides[journal_service] = lambda: JournalService(journal_repository, repository)
    app.dependency_overrides[research_service] = lambda: ResearchService(
        journal_repository, repository, sectors
    )
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": synthetic_bars(300)},
            "SPY": {"meta": listing("SPDR S&P 500 ETF", instrument_type="ETF"), "bars": synthetic_bars(300)},
        }
    )
    market = MarketService(MarketRepository(repository.database), provider=history)
    app.dependency_overrides[market_service] = lambda: market
    sec_repository = SecRepository(repository.database)
    sec = SecDataService(sec_repository, FakeSec())
    fundamentals = FundamentalsService(sec, market)
    app.dependency_overrides[fundamentals_service] = lambda: fundamentals
    app.dependency_overrides[insider_service] = lambda: InsiderService(sec, market)
    app.dependency_overrides[peer_service] = lambda: PeerService(sec, market, fundamentals, sec_repository)
    client = TestClient(app)
    client.history = history  # type: ignore[attr-defined]
    yield client
    app.dependency_overrides.clear()


def test_write_endpoints_require_local_marker(client: TestClient) -> None:
    body = {"symbol": "ACME", "quantity": "1"}
    assert client.post("/api/portfolio/positions", json=body).status_code == 403
    assert client.post("/api/portfolio/demo", json={"confirm": "LOAD DEMO"}).status_code == 403
    assert client.post("/api/activity", json={}).status_code == 403
    assert not [route.path for route in app.routes if "snaptrade" in route.path or "import" in route.path]


def test_default_services_share_one_repository() -> None:
    assert sector_service().repository is portfolio_service().repository
    assert activity_service().repository is portfolio_service().repository


def test_manual_portfolio_workflow(client: TestClient) -> None:
    assert client.get("/api/portfolio").json() == {"status": "empty", "portfolio": None}

    added = client.post(
        "/api/portfolio/positions",
        headers=WRITE,
        json={"symbol": "acme", "quantity": "3", "average_cost": "100", "account_name": "Brokerage"},
    )
    assert added.status_code == 200
    assert added.json()["symbol"] == "ACME"
    client.post("/api/portfolio/positions", headers=WRITE, json={"symbol": "CASH", "quantity": "40"})

    foreign = client.post(
        "/api/portfolio/positions", headers=WRITE, json={"symbol": "XIC.TO", "quantity": "1"}
    )
    assert foreign.status_code == 422
    assert "not a supported US ticker" in foreign.json()["detail"]
    invalid = client.post(
        "/api/portfolio/positions", headers=WRITE, json={"symbol": "ACME", "quantity": "-1"}
    )
    assert invalid.status_code == 422

    portfolio = client.get("/api/portfolio").json()["portfolio"]
    assert portfolio["total_value"] == "400"
    assert portfolio["data_origin"] == "manual"
    assert {row["canonical_symbol"] for row in portfolio["holdings"]} == {"ACME", "USD"}
    assert client.get("/api/portfolio/status").json()["snapshot_count"] == 2

    demo_refused = client.post("/api/portfolio/demo", headers=WRITE, json={"confirm": "LOAD DEMO"})
    assert demo_refused.status_code == 409

    acme = next(row for row in portfolio["holdings"] if row["canonical_symbol"] == "ACME")
    removed = client.delete(f"/api/portfolio/positions/{acme['position_id']}", headers=WRITE)
    assert removed.status_code == 200
    assert removed.json()["removed_symbol"] == "ACME"
    assert len(client.get("/api/portfolio/history").json()["history"]) == 3

    analytics = client.get("/api/analytics").json()["analytics"]
    assert analytics["performance"]["benchmark"] == "S&P 500 Total Return Index"
    assert "currency_exposure" not in analytics

    rejected = client.request(
        "DELETE", "/api/portfolio/local-data", headers=WRITE, json={"confirm": "DELETE"}
    )
    assert rejected.status_code == 422
    deleted = client.request(
        "DELETE", "/api/portfolio/local-data", headers=WRITE, json={"confirm": "DELETE LOCAL DATA"}
    )
    assert deleted.json() == {"status": "deleted", "snapshots": 3}
    assert client.get("/api/portfolio").json()["portfolio"] is None


def test_demo_portfolio_and_activity_ledger(client: TestClient) -> None:
    loaded = client.post("/api/portfolio/demo", headers=WRITE, json={"confirm": "LOAD DEMO"})
    assert loaded.status_code == 200
    portfolio = client.get("/api/portfolio").json()["portfolio"]
    assert portfolio["data_origin"] == "demo"
    assert portfolio["total_positions"] == 9
    assert client.get("/api/portfolio/status").json()["data_origin"] == "demo"

    activity = client.get("/api/activity", params={"activity_type": "DIVIDEND"}).json()
    assert activity["activities"]
    assert all(row["data_origin"] == "demo" for row in activity["activities"])
    assert float(client.get("/api/income").json()["income"]["received"]) > 0

    created = client.post(
        "/api/activity",
        headers=WRITE,
        json={"activity_type": "DEPOSIT", "trade_date": "2026-09-01", "cash_amount": "500"},
    )
    assert created.status_code == 200
    unsupported = client.post(
        "/api/activity",
        headers=WRITE,
        json={"activity_type": "DISTRIBUTION", "trade_date": "2026-09-01", "cash_amount": "1"},
    )
    assert unsupported.status_code == 422
    missing_symbol = client.post(
        "/api/activity",
        headers=WRITE,
        json={"activity_type": "BUY", "trade_date": "2026-09-01", "quantity": "1"},
    )
    assert missing_symbol.status_code == 422
    assert client.delete(f"/api/activity/{created.json()['id']}", headers=WRITE).status_code == 200
    assert client.delete(f"/api/activity/{created.json()['id']}", headers=WRITE).status_code == 404

    apple = next(row for row in portfolio["holdings"] if row["canonical_symbol"] == "AAPL")
    prompts = client.get("/api/research/prompts").json()["prompts"]
    assert "US retail investor" in prompts[0]["prompt_text"]
    pack = client.post(
        "/api/research/packs/preview",
        json={"instrument_id": apple["instrument_id"], "prompt_id": prompts[0]["id"]},
    ).json()["pack"]
    assert "# Manual review request: AAPL" in pack["markdown"]
    assert "CAD" not in pack["markdown"]


def test_market_routes_return_chart_technicals_and_watchlist(client: TestClient) -> None:
    chart = client.get("/api/market/acme/chart", params={"range": "3M"})
    assert chart.status_code == 200
    payload = chart.json()
    assert payload["symbol"] == "ACME"
    assert payload["range"] == "3M"
    assert set(payload["indicators"]) >= {"ema20", "sma200", "rsi14", "macd_histogram"}
    assert client.get("/api/market/ACME/chart", params={"range": "2W"}).status_code == 422
    assert client.get("/api/market/XIC.TO/chart").status_code == 422
    assert client.get("/api/market/NOPE/chart").status_code == 422

    technicals = client.get("/api/market/ACME/technicals").json()
    assert technicals["trend"]["label"] == "Uptrend"

    assert client.post("/api/watchlist", json={"symbol": "ACME"}).status_code == 403
    assert client.post("/api/watchlist", headers=WRITE, json={"symbol": "acme"}).json()["symbol"] == "ACME"
    assert [item["symbol"] for item in client.get("/api/watchlist").json()["items"]] == ["ACME"]
    assert client.delete("/api/watchlist/ACME", headers=WRITE).status_code == 200
    assert client.delete("/api/watchlist/ACME", headers=WRITE).status_code == 404

    client.history.offline = True  # type: ignore[attr-defined]
    outage = client.get("/api/market/NEWCO/chart")
    assert outage.status_code == 502
    assert "Market data is unavailable" in outage.json()["detail"]
    strip = client.get("/api/market/strip").json()
    assert len(strip["items"]) == 10


def test_sec_routes_return_fundamentals_insiders_and_editable_peers(client: TestClient) -> None:
    fundamentals = client.get("/api/market/ACME/fundamentals").json()
    assert fundamentals["applicable"] is True
    assert fundamentals["ttm"]["revenue"]["value"] == 790.0
    insiders = client.get("/api/market/ACME/insiders", params={"days": 90})
    assert insiders.status_code == 200
    assert insiders.json()["summary"]["buyers"] >= 0
    assert client.get("/api/market/ACME/insiders", params={"days": 2}).status_code == 422
    peers = client.get("/api/market/ACME/peers").json()
    assert peers["list_source"] == "SIC"
    assert client.put("/api/market/ACME/peers", json={"symbols": ["SPY"]}).status_code == 403
    edited = client.put("/api/market/ACME/peers", headers=WRITE, json={"symbols": ["spy"]}).json()
    assert edited["peers"] == ["SPY"]
    assert edited["list_source"] == "USER"
    assert client.request("DELETE", "/api/market/ACME/peers", headers=WRITE).json()["list_source"] == "SIC"
    missing = client.get("/api/market/SPY/fundamentals").json()
    assert missing["applicable"] is False


def test_sec_routes_explain_missing_configuration_and_unknown_filers(
    client: TestClient, tmp_path: Path
) -> None:
    unconfigured = SecDataService(SecRepository(Database(tmp_path / "unconfigured.sqlite3")), SecClient(None))
    market = app.dependency_overrides[market_service]()
    app.dependency_overrides[fundamentals_service] = lambda: FundamentalsService(unconfigured, market)
    response = client.get("/api/market/ACME/fundamentals")
    assert response.status_code == 503
    assert "PORTFOLIO_MANAGER_SEC_USER_AGENT" in response.json()["detail"]

    sec_client = FakeSec()
    sec_client.tickers = [row for row in sec_client.tickers if row["ticker"] != "ACME"]
    sec = SecDataService(SecRepository(Database(tmp_path / "missing.sqlite3")), sec_client)
    app.dependency_overrides[fundamentals_service] = lambda: FundamentalsService(sec, market)
    not_found = client.get("/api/market/ACME/fundamentals")
    assert not_found.status_code == 404
    assert "not in SEC's list" in not_found.json()["detail"]

    class Offline(FakeSec):
        def company_tickers(self):  # type: ignore[override]
            raise httpx.ConnectError("nodename nor servname provided")

    offline = SecDataService(SecRepository(Database(tmp_path / "offline.sqlite3")), Offline())
    app.dependency_overrides[fundamentals_service] = lambda: FundamentalsService(offline, market)
    outage = client.get("/api/market/ACME/fundamentals")
    assert outage.status_code == 502
    assert "Couldn't reach SEC EDGAR" in outage.json()["detail"]
