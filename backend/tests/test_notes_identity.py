from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.database import Database
from app.journal_repository import JournalRepository
from app.market_repository import MarketRepository
from app.providers.prices import UnsupportedSymbolError
from app.repository import PortfolioRepository
from app.services.journal import JournalService
from app.services.market import MarketService
from app.services.portfolio import PortfolioService
from fakes import FakeHistory, FakePrices, listing, synthetic_bars

BARS = synthetic_bars(300, base=100, step=0.5)
LAST_CLOSE = BARS[-1]["close"]
LAST_DATE = date.fromisoformat(BARS[-1]["date"])


def _journal(tmp_path: Path) -> tuple[JournalService, PortfolioRepository, MarketService]:
    database = Database(tmp_path / "journal.sqlite3")
    portfolio_repository = PortfolioRepository(database)
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": BARS},
            "WATCH": {"meta": listing("Watchlist Only Inc."), "bars": BARS},
            "BRK-B": {"meta": listing("Berkshire Hathaway Inc."), "bars": BARS},
        }
    )
    market = MarketService(MarketRepository(database), provider=history)
    journal = JournalService(JournalRepository(database), portfolio_repository, market=market)
    return journal, portfolio_repository, market


def test_notes_are_validated_per_symbol_and_editable(tmp_path: Path) -> None:
    journal, _, _ = _journal(tmp_path)
    first = journal.add_note("brk-b", "  Watching $400 as support.  ", "2026-10-12")
    assert (first["symbol"], first["body"], first["pinned_date"], first["author"]) == (
        "BRK.B",
        "Watching $400 as support.",
        "2026-10-12",
        "USER",
    )
    journal.add_note("BRK.B", "Proposed review after earnings.", author="CLAUDE")
    journal.add_note("ACME", "Unrelated note.")
    notes = journal.symbol_journal("BRK.B")["notes"]
    assert [note["author"] for note in notes] == ["CLAUDE", "USER"]

    updated = journal.update_note(first["id"], "Support moved to $410.", None)
    assert updated["body"] == "Support moved to $410."
    assert updated["pinned_date"] is None

    for body, pinned, message in (
        ("   ", None, "needs some text"),
        ("x" * 10_001, None, "limited to 10,000"),
        ("Future", (datetime.now(UTC).date() + timedelta(days=2)).isoformat(), "can't be in the future"),
        ("Bad date", "2026-13-40", "ISO date"),
    ):
        with pytest.raises(ValueError, match=message):
            journal.add_note("ACME", body, pinned)
    with pytest.raises(ValueError, match="author"):
        journal.add_note("ACME", "Text", author="BROKER")
    with pytest.raises(UnsupportedSymbolError):
        journal.add_note("XIC.TO", "Canadian listing")

    journal.delete_note(first["id"])
    with pytest.raises(KeyError):
        journal.delete_note(first["id"])
    with pytest.raises(KeyError):
        journal.update_note(first["id"], "Gone", None)


def test_unheld_tickers_get_an_instrument_and_decisions(tmp_path: Path) -> None:
    journal, portfolio_repository, _ = _journal(tmp_path)
    PortfolioService(portfolio_repository, price_provider=FakePrices()).upsert_position(
        symbol="ACME", quantity="1", average_cost="100", account_name="Brokerage"
    )
    held = portfolio_repository.instrument_by_symbol("ACME")
    assert journal.resolve_symbol("acme") == held["id"]

    assert journal.symbol_journal("WATCH")["instrument_id"] is None
    watch_id = journal.resolve_symbol("WATCH")
    assert journal.resolve_symbol("WATCH") == watch_id
    instrument = portfolio_repository.instrument(watch_id)
    assert (instrument["security_name"], instrument["asset_type"]) == ("Watchlist Only Inc.", "STOCK")

    journal.save_symbol_decision("WATCH", {"decision": "CONSIDER_ADD", "decision_date": "2026-10-20"})
    entry = journal.symbol_journal("WATCH")
    assert entry["instrument_id"] == watch_id
    assert entry["decision"]["decision"] == "CONSIDER_ADD"
    assert journal.repository.decision_history(watch_id)[0]["new_decision"] == "CONSIDER_ADD"
    # Unheld tickers stay out of the portfolio itself.
    assert [row["canonical_symbol"] for row in portfolio_repository.latest_portfolio()["holdings"]] == [
        "ACME"
    ]
    with pytest.raises(UnsupportedSymbolError):
        journal.resolve_symbol("NOPE")


def test_price_triggers_on_unheld_tickers_use_the_cached_daily_close(tmp_path: Path) -> None:
    journal, _, _ = _journal(tmp_path)
    watch_id = journal.resolve_symbol("WATCH")
    journal.create_trigger(watch_id, {"trigger_type": "PRICE_ABOVE", "upper_value": str(LAST_CLOSE - 1)})
    journal.create_trigger(watch_id, {"trigger_type": "PRICE_BELOW", "lower_value": str(LAST_CLOSE - 50)})

    stale_now = datetime.combine(LAST_DATE + timedelta(days=30), datetime.min.time(), UTC)
    journal.evaluate_triggers(now=stale_now)
    assert {row["state"] for row in journal.repository.triggers(watch_id)} == {"ACTIVE"}

    fresh_now = datetime.combine(LAST_DATE + timedelta(days=1), datetime.min.time(), UTC)
    journal.evaluate_triggers(now=fresh_now)
    by_type = {row["trigger_type"]: row for row in journal.repository.triggers(watch_id)}
    assert by_type["PRICE_ABOVE"]["state"] == "TRIGGERED"
    assert Decimal(by_type["PRICE_ABOVE"]["observed_value"]) == Decimal(str(LAST_CLOSE))
    assert by_type["PRICE_ABOVE"]["quote_source"] == "Yahoo Finance chart (daily close)"
    assert by_type["PRICE_ABOVE"]["quote_timestamp"] == LAST_DATE.isoformat()
    assert by_type["PRICE_BELOW"]["state"] == "ACTIVE"
    assert [alert["symbol"] for alert in journal.repository.alerts()] == ["WATCH"]


def test_technical_setup_reports_the_twenty_day_average(tmp_path: Path) -> None:
    _, _, market = _journal(tmp_path)
    trend = market.technicals("ACME")["trend"]
    assert trend["sma20"] == pytest.approx(sum(bar["close"] for bar in BARS[-20:]) / 20)
    assert trend["above_sma20"] is True
