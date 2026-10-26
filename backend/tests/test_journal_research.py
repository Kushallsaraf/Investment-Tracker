from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.database import Database
from app.journal_repository import JournalRepository
from app.repository import PortfolioRepository
from app.services.activities import ActivityService
from app.services.journal import JournalService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sectors import SectorService
from fakes import FakePrices


def build_services(
    tmp_path: Path,
) -> tuple[
    PortfolioRepository,
    JournalRepository,
    JournalService,
    ResearchService,
    str,
]:
    database = Database(tmp_path / "journal.sqlite3")
    portfolio_repository = PortfolioRepository(database)
    PortfolioService(portfolio_repository, price_provider=FakePrices()).upsert_position(
        symbol="ACME", quantity="2", average_cost="50", account_name="Brokerage"
    )
    holding = portfolio_repository.latest_portfolio()["holdings"][0]
    journal_repository = JournalRepository(database)
    journal = JournalService(journal_repository, portfolio_repository)
    sectors = SectorService(portfolio_repository)
    research = ResearchService(journal_repository, portfolio_repository, sectors)
    return portfolio_repository, journal_repository, journal, research, holding["instrument_id"]


def test_decision_history_is_append_only_and_ai_cannot_overwrite_it(tmp_path: Path) -> None:
    _portfolio, repository, journal, research, instrument_id = build_services(tmp_path)
    journal.save_decision(
        instrument_id,
        {"decision": "HOLD", "decision_date": "2026-09-10", "reason": "Synthetic reason"},
    )
    journal.save_decision(
        instrument_id,
        {
            "decision": "CONSIDER_REDUCE",
            "decision_date": "2026-09-11",
            "reason": "Review concentration",
        },
    )
    before = repository.decisions()[0]["decision"]
    research.save_ai_review(
        instrument_id,
        {
            "review_date": "2026-09-11",
            "evidence_as_of": "2026-09-10",
            "suggestion": "CONSIDER_EXIT",
            "disposition": "CONSIDERING",
            "original_markdown": "# Synthetic Claude response",
        },
    )
    assert repository.decisions()[0]["decision"] == before == "CONSIDER_REDUCE"
    history = repository.decision_history(instrument_id)
    assert len(history) == 2
    assert history[0]["previous_decision"] == "HOLD"
    assert history[1]["previous_decision"] is None


def test_trigger_creates_local_alert_and_freezes_snapshot_without_external_action(tmp_path: Path) -> None:
    portfolio, repository, journal, _research, instrument_id = build_services(tmp_path)
    journal.create_trigger(
        instrument_id,
        {
            "trigger_type": "PRICE_ABOVE",
            "upper_value": "100",
            "reason": "Synthetic review threshold",
        },
    )
    trigger = repository.triggers(instrument_id)[0]
    latest = portfolio.latest_portfolio()
    assert trigger["state"] == "TRIGGERED"
    assert trigger["observed_value"] == "120"
    assert trigger["frozen_holding_snapshot_id"] == latest["holding_snapshot_id"]
    assert trigger["frozen_valuation_snapshot_id"] == latest["valuation_snapshot_id"]
    assert "no order" in repository.alerts()[0]["message"].lower()


def test_review_pack_privacy_and_missing_evidence_are_explicit(tmp_path: Path) -> None:
    _portfolio, _repository, journal, research, instrument_id = build_services(tmp_path)
    journal.save_profile(
        instrument_id,
        {
            "portfolio_role": "SPECULATIVE",
            "thesis_strength": 3,
            "why_owned": "Synthetic thesis",
            "supporting_evidence": "Synthetic only",
            "principal_risks": "Synthetic risk",
            "invalidation_conditions": "Synthetic invalidation",
            "maximum_weight": "0.1",
            "source_links": [],
        },
    )
    prompt = research.prompts()[0]
    pack = research.generate_pack(
        instrument_id=instrument_id,
        prompt_id=prompt["id"],
        trigger_id=None,
        privacy={
            "weights_only": True,
            "include_quantities": False,
            "include_dollar_values": False,
            "include_account_name": False,
        },
        save=False,
    )
    markdown = pack["markdown"]
    assert "Quantity:" not in markdown
    assert "Average cost:" not in markdown
    assert "Account:" not in markdown
    assert "Brokerage" not in markdown
    assert "Adjusted total-return performance is not available" in markdown
    assert "Manual copy/export to Claude" in markdown
    assert "No order or brokerage action" in markdown


def test_activity_ledger_validates_records_and_summarizes_income(tmp_path: Path) -> None:
    repository = PortfolioRepository(Database(tmp_path / "activity.sqlite3"))
    activities = ActivityService(repository)
    activities.record(
        {"activity_type": "DIVIDEND", "symbol": "acme", "trade_date": "2026-06-30", "cash_amount": "12.50"}
    )
    activities.record(
        {"activity_type": "DIVIDEND", "symbol": "ACME", "trade_date": "2026-03-31", "cash_amount": "12"}
    )
    activities.record({"activity_type": "INTEREST", "trade_date": "2026-07-15", "cash_amount": "3.10"})
    activities.record(
        {"activity_type": "WITHHOLDING_TAX", "trade_date": "2026-06-30", "cash_amount": "-1.25"}
    )
    activities.record(
        {"activity_type": "DIVIDEND", "symbol": "ACME", "trade_date": "2024-01-02", "cash_amount": "9"}
    )
    buy_id = activities.record(
        {"activity_type": "BUY", "symbol": "BRK-B", "trade_date": "2026-08-01", "quantity": "1",
         "price": "400"}
    )

    with pytest.raises(ValueError, match="needs a symbol"):
        activities.record({"activity_type": "DIVIDEND", "trade_date": "2026-06-30", "cash_amount": "1"})
    with pytest.raises(ValueError, match="not a supported US ticker"):
        activities.record({"activity_type": "BUY", "symbol": "XIC.TO", "trade_date": "2026-06-30"})
    with pytest.raises(ValueError, match="ISO date"):
        activities.record({"activity_type": "FEE", "trade_date": "yesterday", "cash_amount": "-1"})
    with pytest.raises(ValueError, match="Cash amount is required"):
        activities.record({"activity_type": "DEPOSIT", "trade_date": "2026-06-30"})

    listed = activities.list(symbol="brk")
    assert [row["symbol"] for row in listed["activities"]] == ["BRK.B"]
    assert activities.list()["coverage"]["count"] == 6

    income = activities.income(now=datetime(2026, 9, 1, tzinfo=UTC))
    assert income["received"] == "27.60"
    assert income["withholding_tax"] == "1.25"
    assert income["income_by_holding"] == [
        {"symbol": "ACME", "amount": "24.50"},
        {"symbol": "CASH", "amount": "3.10"},
    ]

    activities.delete(buy_id)
    assert activities.list()["coverage"]["count"] == 5
    with pytest.raises(KeyError):
        activities.delete(buy_id)
