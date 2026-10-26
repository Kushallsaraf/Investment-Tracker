from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.database import Database
from app.repository import PortfolioRepository
from app.services.portfolio import PortfolioService
from app.services.sectors import SectorService
from fakes import FakePrices

SYNTHETIC_PROFILE = {
    "SYNE": {
        "name": "Synthetic Equity ETF",
        "issuer": "Synthetic Issuer",
        "as_of": "2026-08-31",
        "verified_on": "2026-09-08",
        "source_url": "https://example.invalid/syne",
        "method": "Synthetic issuer-published sector allocation",
        "sectors": {
            "Information Technology": 60,
            "Health Care": 39.9,
            "Cash": 0.1,
        },
    }
}


def _portfolio(tmp_path: Path) -> PortfolioRepository:
    repository = PortfolioRepository(Database(tmp_path / "sectors.sqlite3"))
    service = PortfolioService(repository, price_provider=FakePrices({"ACME": "25", "SYNE": "10"}))
    service.upsert_position(symbol="SYNE", quantity="10", average_cost="8", account_name="")
    service.upsert_position(symbol="ACME", quantity="2", average_cost="20", account_name="")
    service.upsert_position(symbol="CASH", quantity="50", average_cost=None, account_name="")
    return repository


def _profiles(tmp_path: Path) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(SYNTHETIC_PROFILE), encoding="utf-8")
    return path


def test_etf_look_through_and_direct_stock_sector_coverage(tmp_path: Path) -> None:
    repository = _portfolio(tmp_path)
    sectors = SectorService(repository, profile_path=_profiles(tmp_path), today=date(2026, 9, 8))

    initial = sectors.latest()
    assert initial is not None
    by_sector = {row["sector"]: row for row in initial["categories"]}
    assert by_sector["Information Technology"]["market_value"] == "60.000000"
    assert by_sector["Unknown"]["market_value"] == "50.000000"
    assert by_sector["Cash"]["market_value"] == "50.100000"
    assert initial["coverage_pct"] == "0.750000"
    assert initial["etf_coverage_pct"] == "1.000000"
    assert initial["evidence"][0]["as_of"] == "2026-08-31"
    assert initial["evidence"][0]["stale"] is False

    stock = next(row for row in repository.latest_portfolio()["holdings"] if row["asset_type"] == "STOCK")
    sectors.update_direct_sector(stock["instrument_id"], "Industrials")
    updated = sectors.latest()
    assert updated is not None
    assert updated["coverage_pct"] == "1.000000"
    assert all(row["sector"] != "Unknown" for row in updated["categories"])


def test_old_issuer_evidence_is_flagged(tmp_path: Path) -> None:
    repository = _portfolio(tmp_path)
    analysis = SectorService(repository, profile_path=_profiles(tmp_path), today=date(2027, 3, 1)).latest()
    assert analysis is not None
    assert analysis["evidence"][0]["stale"] is True
    assert any("issuer sector evidence" in warning for warning in analysis["warnings"])


def test_etf_without_profile_remains_unknown(tmp_path: Path) -> None:
    repository = _portfolio(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    analysis = SectorService(repository, profile_path=empty, today=date(2026, 9, 8)).latest()
    by_sector = {row["sector"]: row for row in analysis["categories"]}
    assert by_sector["Unknown"]["market_value"] == "150.000000"
    assert analysis["evidence"][0]["method"] == "No supported issuer profile"
