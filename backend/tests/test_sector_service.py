from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from app.database import Database
from app.repository import PortfolioRepository
from app.services.imports import ImportService
from app.services.portfolio import PortfolioService
from app.services.sectors import SectorService


class SectorTestPrices:
    def quote(self, instrument: dict) -> dict:
        prices = {"AIQ.TO": "10", "ACME.TO": "25", "ZEM.TO": "30"}
        now = datetime.now(UTC).isoformat()
        return {
            "price": prices[instrument["canonical_symbol"]],
            "currency": "CAD",
            "observed_at": now,
            "fetched_at": now,
            "source": "Synthetic test price",
            "source_url": None,
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": False,
        }


class NoFx:
    def usd_cad(self) -> dict:
        raise AssertionError("FX should not be requested")


def test_etf_look_through_and_direct_stock_sector_coverage(tmp_path: Path) -> None:
    repository = PortfolioRepository(Database(tmp_path / "sectors.sqlite3"))
    imports = ImportService(repository)
    source = tmp_path / "holdings.csv"
    source.write_text(
        "Account Type,Account Number,Symbol,Security Name,Security Type,"
        "Exchange,Currency,Quantity,Average Cost\n"
        "TFSA,SYNTHETIC,AIQ,Global X AI ETF,ETF,TSX,CAD,10,8\n"
        "TFSA,SYNTHETIC,ACME,Acme Inc,Stock,TSX,CAD,2,20\n"
        "TFSA,SYNTHETIC,CAD,Canadian Dollar,CURRENCY,,CAD,50,1\n",
        encoding="utf-8",
    )
    preview = imports.preview(source)
    snapshot_id = imports.confirm(preview["draft_id"], accept_warnings=True)
    PortfolioService(
        repository, price_provider=SectorTestPrices(), fx_provider=NoFx()
    ).refresh(snapshot_id)
    sectors = SectorService(repository, today=date(2026, 9, 8))

    initial = sectors.latest()
    assert initial is not None
    by_sector = {row["sector"]: row for row in initial["categories"]}
    assert by_sector["Information Technology"]["market_value_cad"] == "67.870000"
    assert by_sector["Unknown"]["market_value_cad"] == "50.000000"
    assert by_sector["Cash"]["market_value_cad"] == "50.040000"
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
    repository = PortfolioRepository(Database(tmp_path / "stale.sqlite3"))
    imports = ImportService(repository)
    source = tmp_path / "holdings.csv"
    source.write_text(
        "Account Type,Symbol,Security Name,Security Type,Exchange,Currency,Quantity\n"
        "TFSA,ZEM,BMO Emerging Markets ETF,ETF,TSX,CAD,1\n",
        encoding="utf-8",
    )
    preview = imports.preview(source)
    snapshot_id = imports.confirm(preview["draft_id"], accept_warnings=True)
    PortfolioService(
        repository, price_provider=SectorTestPrices(), fx_provider=NoFx()
    ).refresh(snapshot_id)

    analysis = SectorService(repository, today=date(2026, 9, 8)).latest()
    assert analysis is not None
    assert analysis["evidence"][0]["stale"] is True
    assert any("issuer sector evidence" in warning for warning in analysis["warnings"])
