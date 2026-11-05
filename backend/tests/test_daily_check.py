from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.database import Database
from app.services import daily_check
from app.services.container import Services, build_services
from app.services.daily_check import notification_for, run_check
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars

BARS = synthetic_bars(300, base=100, step=0.5)
LAST_CLOSE = BARS[-1]["close"]
FRESH = datetime.combine(date.fromisoformat(BARS[-1]["date"]) + timedelta(days=1), datetime.min.time(), UTC)


def _services(tmp_path: Path) -> tuple[Services, FakeHistory]:
    history = FakeHistory(
        {
            "WATCH": {"meta": listing("Watchlist Only Inc."), "bars": BARS},
            "QUIET": {"meta": listing("Quiet Corp."), "bars": BARS},
        }
    )
    services = build_services(
        Database(tmp_path / "check.sqlite3"), history=history, prices=FakePrices(), sec_client=FakeSec()
    )
    return services, history


def test_check_refreshes_open_triggers_and_notifies_new_alerts_once(tmp_path: Path) -> None:
    services, history = _services(tmp_path)
    plan = services.exit_plans.propose(
        "WATCH",
        target_price=str(LAST_CLOSE - 1),
        stop_price=str(LAST_CLOSE - 40),
        reasoning="Take profits near the prior high.\nRevisit after earnings.",
        today=date(2026, 11, 4),
    )
    services.exit_plans.accept(plan["id"], today=date(2026, 11, 4))
    quiet = services.journal.resolve_symbol("QUIET")
    services.journal.create_trigger(quiet, {"trigger_type": "PRICE_BELOW", "lower_value": "1"})
    history.calls.clear()

    sent: list[tuple[str, str, str]] = []
    result = run_check(services, notify=lambda *message: sent.append(message), now=FRESH)
    assert result["refreshed"] == ["QUIET", "WATCH"]
    assert result["failed"] == {}
    assert result["open_triggers"] == 3
    assert [alert["trigger_type"] for alert in result["due_alerts"]] == ["PRICE_ABOVE"]
    assert result["notified"] == 1
    title, subtitle, body = sent[0]
    assert (title, subtitle) == ("Investment Tracker", "WATCH · review due")
    assert "at or above the exit-plan target" in body
    assert "Reasoning: Take profits near the prior high." in body

    # Each alert is sent once.
    again = run_check(services, notify=lambda *message: sent.append(message), now=FRESH)
    assert again["due_alerts"] == []
    assert len(sent) == 1
    assert services.journal_repository.alerts()[0]["notified_at"] is not None


def test_alerts_found_by_the_dashboard_are_still_notified(tmp_path: Path) -> None:
    services, _ = _services(tmp_path)
    watch = services.journal.resolve_symbol("WATCH")
    services.journal.create_trigger(watch, {"trigger_type": "PRICE_ABOVE", "upper_value": "1"})
    services.journal.evaluate_triggers(now=FRESH)  # what opening the dashboard does
    assert len(services.journal_repository.alerts()) == 1

    preview = run_check(services, notify=None, now=FRESH)
    assert len(preview["due_alerts"]) == 1
    assert preview["notified"] == 0

    sent: list[tuple[str, str, str]] = []
    result = run_check(services, notify=lambda *message: sent.append(message), now=FRESH)
    assert result["notified"] == 1
    assert sent[0][1] == "WATCH · review due"


def test_check_reports_outages_and_retries_failed_notifications(tmp_path: Path) -> None:
    services, history = _services(tmp_path)
    watch = services.journal.resolve_symbol("WATCH")
    services.journal.create_trigger(watch, {"trigger_type": "PRICE_ABOVE", "upper_value": "1"})
    # A day later the price source is down, so the cached close is used and the outage reported.
    history.offline = True
    services.market.clock = lambda: datetime.now(UTC) + timedelta(days=1)

    def broken_notifier(*_: str) -> None:
        raise OSError("osascript is missing")

    result = run_check(services, notify=broken_notifier, now=FRESH)
    assert result["refreshed"] == []
    assert "stale" in result["failed"]["WATCH"]
    assert (len(result["due_alerts"]), result["notified"]) == (1, 0)
    retry = run_check(services, notify=lambda *_: None, now=FRESH)
    assert retry["notified"] == 1


def test_notifications_shorten_long_reasoning_and_quote_safely(monkeypatch: Any) -> None:
    alert = {"symbol": "GFS", "message": "GFS closed at 48.", "exit_plan_reasoning": "x" * 400}
    _, _, body = notification_for(alert)
    assert body.endswith("…")
    assert len(body) < 220

    commands: list[list[str]] = []
    monkeypatch.setattr(daily_check.subprocess, "run", lambda command, **_: commands.append(command))
    daily_check.macos_notify("Investment Tracker", 'GFS "test"', "Line one\nline two")
    script = commands[0][2]
    assert commands[0][:2] == ["osascript", "-e"]
    assert 'subtitle "GFS \\"test\\""' in script
    assert "Line one line two" in script
