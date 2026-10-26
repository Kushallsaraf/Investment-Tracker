from __future__ import annotations

from pathlib import Path

import pytest
from app.database import Database
from app.providers.prices import UnsupportedSymbolError
from app.repository import PortfolioRepository
from app.services.portfolio import PortfolioService
from fakes import FakePrices


def _service(tmp_path: Path, prices: FakePrices | None = None) -> PortfolioService:
    repository = PortfolioRepository(Database(tmp_path / "portfolio.sqlite3"))
    return PortfolioService(repository, price_provider=prices or FakePrices())


def test_manual_positions_are_valued_in_usd(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_position(symbol="acme", quantity="2", average_cost="100", account_name="Roth IRA")
    service.upsert_position(symbol="SYNE", quantity="4", average_cost=None, account_name="Roth IRA")
    service.upsert_position(symbol="cash", quantity="60", average_cost=None, account_name="Roth IRA")

    portfolio = service.latest()
    assert portfolio is not None
    assert portfolio["total_value"] == "500"
    assert portfolio["data_origin"] == "manual"
    by_symbol = {row["canonical_symbol"]: row for row in portfolio["holdings"]}
    assert by_symbol["ACME"]["market_value"] == "240"
    assert by_symbol["ACME"]["unrealized_gain_loss"] == "40"
    assert by_symbol["ACME"]["account_name"] == "Roth IRA"
    assert by_symbol["SYNE"]["unrealized_gain_loss"] is None
    assert by_symbol["USD"]["asset_type"] == "CASH"
    assert by_symbol["USD"]["price_source"] == "Currency face value"
    assert by_symbol["USD"]["unrealized_gain_loss"] is None
    assert service.status()["snapshot_count"] == 3


def test_upsert_replaces_same_symbol_in_same_account_only(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_position(symbol="ACME", quantity="2", average_cost="100", account_name="Brokerage")
    service.upsert_position(symbol="ACME", quantity="5", average_cost="110", account_name="Brokerage")
    service.upsert_position(symbol="ACME", quantity="1", average_cost="90", account_name="Roth IRA")

    holdings = service.latest()["holdings"]
    quantities = sorted((row["account_name"], row["quantity"]) for row in holdings)
    assert quantities == [("Brokerage", "5"), ("Roth IRA", "1")]
    assert len(service.history()) == 3


def test_invalid_positions_are_rejected_before_storage(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="positive"):
        service.upsert_position(symbol="ACME", quantity="0", average_cost=None, account_name="")
    with pytest.raises(ValueError, match="non-negative"):
        service.upsert_position(symbol="ACME", quantity="1", average_cost="-3", account_name="")
    with pytest.raises(UnsupportedSymbolError):
        service.upsert_position(symbol="XIC.TO", quantity="1", average_cost=None, account_name="")
    with pytest.raises(UnsupportedSymbolError):
        service.upsert_position(symbol="NOPE", quantity="1", average_cost=None, account_name="")
    assert service.latest() is None


def test_missing_price_is_explicit_and_excluded_from_total(tmp_path: Path) -> None:
    prices = FakePrices()
    service = _service(tmp_path, prices)
    service.upsert_position(symbol="ACME", quantity="1", average_cost="100", account_name="")
    del prices.prices["SYNE"]
    service.upsert_position(symbol="SYNE", quantity="1", average_cost="40", account_name="")

    portfolio = service.latest()
    assert portfolio["total_value"] == "120"
    assert portfolio["priced_positions"] == 1
    missing = next(row for row in portfolio["holdings"] if row["canonical_symbol"] == "SYNE")
    assert missing["data_status"] == "missing"
    assert missing["market_value"] is None
    assert any("SYNE: latest price unavailable" in warning for warning in portfolio["warnings"])


def test_removing_a_row_creates_a_new_snapshot_and_keeps_history(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_position(symbol="ACME", quantity="1", average_cost=None, account_name="")
    service.upsert_position(symbol="SYNE", quantity="1", average_cost=None, account_name="")
    acme = next(row for row in service.latest()["holdings"] if row["canonical_symbol"] == "ACME")

    result = service.remove_position(acme["position_id"])
    assert result["removed_symbol"] == "ACME"
    assert [row["canonical_symbol"] for row in service.latest()["holdings"]] == ["SYNE"]
    assert len(service.history()) == 3
    with pytest.raises(ValueError, match="portfolio changed"):
        service.remove_position(acme["position_id"])
    with pytest.raises(KeyError):
        service.remove_position("unknown")


def test_demo_portfolio_loads_reloads_and_refuses_to_mix_with_manual_data(tmp_path: Path) -> None:
    demo_symbols = ("AAPL", "MSFT", "NVDA", "JPM", "JNJ", "XOM", "VOO", "QQQ")
    prices = FakePrices({symbol: "100" for symbol in demo_symbols})
    service = _service(tmp_path, prices)
    service.load_demo()
    first = service.latest()
    assert first["data_origin"] == "demo"
    assert first["total_positions"] == 9
    assert service.repository.activity_count("demo") > 0
    tech = next(row for row in first["holdings"] if row["canonical_symbol"] == "AAPL")
    assert tech["manual_sector"] == "Information Technology"

    activity_count = service.repository.activity_count("demo")
    service.load_demo()
    assert service.repository.activity_count("demo") == activity_count
    assert service.status()["snapshot_count"] == 1

    assert service.delete_data() == 1
    assert service.latest() is None
    prices.prices["ACME"] = "120"
    service.upsert_position(symbol="ACME", quantity="1", average_cost=None, account_name="")
    with pytest.raises(ValueError, match="Delete local portfolio data"):
        service.load_demo()
