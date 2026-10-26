from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.database import Database
from app.journal_repository import JournalRepository
from app.main import (
    activity_service,
    analytics_service,
    app,
    journal_service,
    market_service,
    portfolio_service,
    research_service,
    sector_service,
)
from app.market_repository import MarketRepository
from app.repository import PortfolioRepository
from app.services.activities import ActivityService
from app.services.analytics import AnalyticsService
from app.services.journal import JournalService
from app.services.market import MarketService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sectors import SectorService
from fakes import FakeHistory, FakePrices, listing, synthetic_bars
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
