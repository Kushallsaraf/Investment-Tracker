from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database import Database
from app.main import app, portfolio_service, sector_service, snaptrade_service
from app.repository import PortfolioRepository
from app.services.imports import ImportService
from app.services.portfolio import PortfolioService
from app.services.sectors import SectorService
from app.services.snaptrade import SnapTradeSyncService
from fastapi.testclient import TestClient

CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
ACCOUNT_ID = "22222222-2222-4222-8222-222222222222"
AS_OF = "2026-09-10T14:30:00+00:00"
FIXED_NOW = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)


class OnePrice:
    source = "Synthetic quote"
    supports_automatic_refresh = False
    automatic_refresh_seconds = None

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        now = FIXED_NOW.isoformat()
        return {
            "price": "41.25" if instrument["asset_type"] != "CASH" else "1",
            "currency": instrument["trading_currency"],
            "observed_at": now,
            "fetched_at": now,
            "source": self.source,
            "source_url": None,
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": False,
        }


class UnusedFx:
    def usd_cad(self) -> dict[str, Any]:
        raise AssertionError("FX should not be requested for a CAD-only portfolio")


class SyntheticSnapTrade:
    def __init__(self) -> None:
        self.disconnected: list[str] = []

    def create_connection_portal(self, redirect_uri: str) -> str:
        assert redirect_uri.startswith("http://127.0.0.1:")
        return "https://app.snaptrade.com/synthetic-read-only-portal"

    def list_connections(self) -> list[dict[str, Any]]:
        return [
            {
                "id": CONNECTION_ID,
                "type": "read",
                "disabled": False,
                "brokerage": {"slug": "WEALTHSIMPLE", "display_name": "Wealthsimple"},
            }
        ]

    def list_accounts(self) -> list[dict[str, Any]]:
        return [
            {
                "id": ACCOUNT_ID,
                "brokerage_authorization": CONNECTION_ID,
                "number": "SENSITIVE-ACCOUNT-NUMBER",
                "name": "Self-directed TFSA",
                "raw_type": "TFSA",
                "sync_status": {
                    "holdings": {
                        "last_successful_sync": AS_OF,
                        "holdings_unavailable": False,
                    }
                },
            }
        ]

    def list_positions(self, account_id: str) -> dict[str, Any]:
        assert account_id == ACCOUNT_ID
        return {
            "data_freshness": {"as_of": AS_OF},
            "results": [
                {
                    "instrument": {
                        "kind": "etf",
                        "symbol": "XIC",
                        "description": "iShares Core S&P/TSX Capped Composite Index ETF",
                        "currency": "CAD",
                        "exchange": "XTSE",
                    },
                    "units": "10",
                    "cost_basis": "31",
                    "currency": "CAD",
                    "as_of": AS_OF,
                }
            ],
        }

    def list_balances(self, account_id: str) -> list[dict[str, Any]]:
        assert account_id == ACCOUNT_ID
        return [{"currency": {"code": "CAD"}, "cash": "25"}]

    def disconnect(self, connection_id: str) -> None:
        self.disconnected.append(connection_id)


def _client(
    tmp_path: Path,
) -> tuple[TestClient, PortfolioRepository, PortfolioService, SyntheticSnapTrade]:
    repository = PortfolioRepository(Database(tmp_path / "api.sqlite3"))
    portfolio = PortfolioService(repository, price_provider=OnePrice(), fx_provider=UnusedFx())
    synthetic = SyntheticSnapTrade()
    snaptrade = SnapTradeSyncService(
        repository,
        portfolio,
        synthetic,
        enabled=True,
        redirect_uri="http://127.0.0.1:5173/?snaptrade=connected",
        local_secret_path=tmp_path / "alias-secret.key",
        clock=lambda: FIXED_NOW,
    )
    app.dependency_overrides[portfolio_service] = lambda: portfolio
    app.dependency_overrides[sector_service] = lambda: SectorService(repository)
    app.dependency_overrides[snaptrade_service] = lambda: snaptrade
    return TestClient(app), repository, portfolio, synthetic


def _create_legacy_snapshot(
    tmp_path: Path,
    repository: PortfolioRepository,
    portfolio: PortfolioService,
) -> str:
    source = tmp_path / "legacy.csv"
    source.write_text(
        "Account Type,Account Number,Symbol,Security Name,Security Type,"
        "Exchange,Currency,Quantity,Average Cost\n"
        "TFSA,LEGACY-SYNTHETIC,XIC,iShares Core ETF,ETF,TSX,CAD,9,30\n",
        encoding="utf-8",
    )
    imports = ImportService(repository)
    preview = imports.preview(source)
    snapshot_id = imports.confirm(preview["draft_id"], accept_warnings=True)
    portfolio.refresh(snapshot_id)
    return snapshot_id


def test_write_endpoints_require_local_marker_and_csv_routes_are_inactive(tmp_path: Path) -> None:
    client, _, _, _ = _client(tmp_path)
    assert client.post("/api/snaptrade/sync/preview").status_code == 403
    legacy_route = client.post(
        "/api/imports/preview",
        headers={"X-Portfolio-Manager": "local-ui"},
    )
    assert legacy_route.status_code in {404, 405}
    app.dependency_overrides.clear()


def test_default_services_share_one_repository() -> None:
    assert snaptrade_service().repository is portfolio_service().repository
    assert sector_service().repository is portfolio_service().repository


def test_snaptrade_preview_apply_disconnect_and_local_deletion(tmp_path: Path) -> None:
    client, repository, portfolio, synthetic = _client(tmp_path)
    legacy_snapshot_id = _create_legacy_snapshot(tmp_path, repository, portfolio)

    portal = client.post(
        "/api/snaptrade/portal", headers={"X-Portfolio-Manager": "local-ui"}
    )
    assert portal.status_code == 200
    assert portal.json()["redirect_uri"].startswith("https://app.snaptrade.com/")

    preview_response = client.post(
        "/api/snaptrade/sync/preview", headers={"X-Portfolio-Manager": "local-ui"}
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert len(preview["changes"]["quantity_changes"]) == 1
    assert len(preview["changes"]["cost_basis_changes"]) == 1
    assert len(preview["changes"]["cash_changes"]) == 1
    assert preview["can_apply"] is True
    assert ACCOUNT_ID not in preview_response.text
    assert "SENSITIVE-ACCOUNT-NUMBER" not in preview_response.text

    recovered_preview = client.get("/api/snaptrade/sync/pending")
    assert recovered_preview.status_code == 200
    assert recovered_preview.json()["preview"]["preview_id"] == preview["preview_id"]
    assert ACCOUNT_ID not in recovered_preview.text
    assert "SENSITIVE-ACCOUNT-NUMBER" not in recovered_preview.text

    bad_confirmation = client.post(
        f"/api/snaptrade/sync/{preview['preview_id']}/apply",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "yes"},
    )
    assert bad_confirmation.status_code == 422
    applied = client.post(
        f"/api/snaptrade/sync/{preview['preview_id']}/apply",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "APPLY"},
    )
    assert applied.status_code == 200
    assert client.get("/api/snaptrade/sync/pending").json()["preview"] is None
    dashboard = client.get("/api/portfolio").json()["portfolio"]
    assert dashboard["total_cad"] == "437.50"
    assert {row["canonical_symbol"] for row in dashboard["holdings"]} == {
        "XIC.TO",
        "CASH-CAD",
    }
    assert dashboard["holdings"][0]["price_source"] in {"Synthetic quote", "Currency face value"}
    assert len(client.get("/api/portfolio/history").json()["history"]) == 2

    second_preview = client.post(
        "/api/snaptrade/sync/preview", headers={"X-Portfolio-Manager": "local-ui"}
    )
    assert second_preview.status_code == 429
    assert int(second_preview.headers["retry-after"]) >= 1

    rejected_disconnect = client.post(
        "/api/snaptrade/disconnect",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "yes"},
    )
    assert rejected_disconnect.status_code == 422
    assert synthetic.disconnected == []

    disconnect = client.post(
        "/api/snaptrade/disconnect",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "DISCONNECT"},
    )
    assert disconnect.status_code == 200
    assert synthetic.disconnected == [CONNECTION_ID]

    rejected_deletion = client.request(
        "DELETE",
        "/api/snaptrade/local-data",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "DELETE"},
    )
    assert rejected_deletion.status_code == 422
    assert len(client.get("/api/portfolio/history").json()["history"]) == 2

    deleted = client.request(
        "DELETE",
        "/api/snaptrade/local-data",
        headers={"X-Portfolio-Manager": "local-ui"},
        json={"confirm": "DELETE LOCAL DATA"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["snapshots"] == 1
    restored = client.get("/api/portfolio").json()["portfolio"]
    assert restored["holding_snapshot_id"] == legacy_snapshot_id
    assert restored["total_cad"] == "371.25"

    raw_database = repository.database.path.read_bytes().decode("latin-1", errors="ignore")
    assert ACCOUNT_ID not in raw_database
    assert CONNECTION_ID not in raw_database
    assert "SENSITIVE-ACCOUNT-NUMBER" not in raw_database
    app.dependency_overrides.clear()
