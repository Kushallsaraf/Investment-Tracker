from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.database import Database
from app.repository import PortfolioRepository
from app.services.imports import ImportService
from app.services.portfolio import PortfolioService


class FakePrices:
    def quote(self, instrument: dict) -> dict:
        prices = {"XIC.TO": ("40", "CAD"), "AAPL": ("200", "USD")}
        price, currency = prices[instrument["canonical_symbol"]]
        now = datetime.now(UTC).isoformat()
        return {
            "price": price,
            "currency": currency,
            "observed_at": now,
            "fetched_at": now,
            "source": "Synthetic test prices",
            "source_url": None,
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": False,
        }


class FakeFx:
    def usd_cad(self) -> dict:
        now = datetime.now(UTC).isoformat()
        return {
            "base_currency": "USD",
            "quote_currency": "CAD",
            "rate": "1.35",
            "observed_at": now,
            "fetched_at": now,
            "source": "Synthetic Bank of Canada fixture",
            "source_url": None,
            "stale": False,
        }


def _accepted_snapshot(tmp_path: Path) -> tuple[PortfolioRepository, str]:
    repository = PortfolioRepository(Database(tmp_path / "portfolio.sqlite3"))
    imports = ImportService(repository)
    source = tmp_path / "holdings.csv"
    source.write_text(
        "Account Type,Account Number,Symbol,Security Name,Security Type,"
        "Exchange,Currency,Quantity,Average Cost\n"
        "TFSA,SYNTHETIC-1,XIC,iShares Core ETF,ETF,TSX,CAD,10,30\n"
        "RRSP,SYNTHETIC-2,AAPL,Apple Inc,Stock,NASDAQ,USD,2,150\n",
        encoding="utf-8",
    )
    preview = imports.preview(source)
    return repository, imports.confirm(preview["draft_id"], accept_warnings=True)


def test_cad_and_usd_positions_are_valued_in_cad(tmp_path: Path) -> None:
    repository, holding_snapshot_id = _accepted_snapshot(tmp_path)
    service = PortfolioService(repository, price_provider=FakePrices(), fx_provider=FakeFx())

    service.refresh(holding_snapshot_id)
    portfolio = service.latest()

    assert portfolio is not None
    assert portfolio["total_cad"] == "940.00"
    assert portfolio["priced_positions"] == 2
    assert portfolio["position_coverage_pct"] == "1"
    assert {row["canonical_symbol"] for row in portfolio["holdings"]} == {"XIC.TO", "AAPL"}
    apple = next(row for row in portfolio["holdings"] if row["canonical_symbol"] == "AAPL")
    assert apple["market_value_cad"] == "540.00"
    assert apple["unrealized_gain_loss_cad"] == "135.00"


class FailingPrices:
    def quote(self, instrument: dict) -> dict:
        raise RuntimeError("synthetic outage")


def test_imported_price_fallback_is_explicitly_stale(tmp_path: Path) -> None:
    repository = PortfolioRepository(Database(tmp_path / "portfolio.sqlite3"))
    imports = ImportService(repository)
    source = tmp_path / "holdings.csv"
    source.write_text(
        "Account Type,Symbol,Security Type,Exchange,Currency,Quantity,Average Cost,Market Price\n"
        "TFSA,XIC,ETF,TSX,CAD,10,30,35\n",
        encoding="utf-8",
    )
    preview = imports.preview(source)
    holding_snapshot_id = imports.confirm(preview["draft_id"], accept_warnings=True)
    service = PortfolioService(repository, price_provider=FailingPrices(), fx_provider=FakeFx())

    service.refresh(holding_snapshot_id)
    portfolio = service.latest()

    assert portfolio is not None
    assert portfolio["holdings"][0]["data_status"] == "imported_stale"
    assert portfolio["holdings"][0]["quote_status"] == "imported"
    assert any("using the imported price" in warning for warning in portfolio["warnings"])


def test_cash_is_valued_at_face_value_without_market_lookup(tmp_path: Path) -> None:
    repository = PortfolioRepository(Database(tmp_path / "cash.sqlite3"))
    imports = ImportService(repository)
    source = tmp_path / "cash-holdings.csv"
    source.write_text(
        "Account Type,Account Number,Symbol,Security Name,Security Type,"
        "Exchange,Currency,Quantity,Average Cost\n"
        "TFSA,SYNTHETIC-1,XIC,Synthetic ETF,ETF,TSX,CAD,10,30\n"
        "TFSA,SYNTHETIC-1,CAD,Canadian Dollar,CURRENCY,,CAD,100,1\n",
        encoding="utf-8",
    )
    preview = imports.preview(source)
    holding_snapshot_id = imports.confirm(preview["draft_id"], accept_warnings=True)
    service = PortfolioService(repository, price_provider=FakePrices(), fx_provider=FakeFx())

    service.refresh(holding_snapshot_id)
    portfolio = service.latest()

    assert portfolio is not None
    assert portfolio["total_cad"] == "500"
    cash = next(row for row in portfolio["holdings"] if row["asset_type"] == "CASH")
    assert cash["canonical_symbol"] == "CASH-CAD"
    assert cash["price"] == "1"
    assert cash["quote_status"] == "not_applicable"
    assert cash["price_source"] == "Currency face value"
