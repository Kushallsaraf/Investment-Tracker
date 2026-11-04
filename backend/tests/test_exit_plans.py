from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from app.database import Database
from app.services.container import Services, build_services
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars

BARS = synthetic_bars(300, base=100, step=0.5)
LAST_CLOSE = BARS[-1]["close"]
LAST_DATE = date.fromisoformat(BARS[-1]["date"])
TODAY = date(2026, 11, 4)


def _services(tmp_path: Path) -> Services:
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": BARS},
            "WATCH": {"meta": listing("Watchlist Only Inc."), "bars": BARS},
        }
    )
    return build_services(
        Database(tmp_path / "exit.sqlite3"), history=history, prices=FakePrices(), sec_client=FakeSec()
    )


def _propose(services: Services, symbol: str = "WATCH", **overrides: object) -> dict:
    values = {
        "target_price": str(round(LAST_CLOSE + 20, 2)),
        "stop_price": str(round(LAST_CLOSE - 15, 2)),
        "review_date": "2027-02-01",
        "reasoning": "Prior resistance near the target; the stop sits under the 200-day average.",
    }
    values.update(overrides)
    return services.exit_plans.propose(symbol, today=TODAY, **values)  # type: ignore[arg-type]


def test_claude_proposals_are_validated_and_never_change_the_decision(tmp_path: Path) -> None:
    services = _services(tmp_path)
    plan = _propose(services, "watch")
    assert plan["symbol"] == "WATCH"
    assert (plan["status"], plan["proposed_by"]) == ("PROPOSED", "CLAUDE")
    assert plan["reference_price"] == f"{LAST_CLOSE:.2f}"
    assert plan["reference_date"] == LAST_DATE.isoformat()
    # A proposal creates no triggers, notes, or decisions.
    journal = services.journal.symbol_journal("WATCH")
    assert (journal["decision"], journal["triggers"], journal["notes"]) == (None, [], [])
    assert [row["id"] for row in journal["exit_plans"]] == [plan["id"]]

    replacement = _propose(services, target_price="999")
    statuses = {row["id"]: row["status"] for row in services.exit_plans.plans("WATCH")}
    assert statuses == {plan["id"]: "SUPERSEDED", replacement["id"]: "PROPOSED"}

    for overrides, message in (
        ({"target_price": None, "stop_price": None, "review_date": None}, "needs a target"),
        ({"target_price": "90", "stop_price": "95"}, "above the stop"),
        ({"stop_price": "-1"}, "positive price"),
        ({"review_date": "2026-01-01"}, "in the past"),
        ({"review_date": "02/01/2027"}, "ISO date"),
        ({"reasoning": "   "}, "reasoning"),
    ):
        with pytest.raises(ValueError, match=message):
            _propose(services, **overrides)
    with pytest.raises(ValueError, match="author"):
        _propose(services, proposed_by="BROKER")


def test_accepting_creates_triggers_a_note_and_a_history_entry(tmp_path: Path) -> None:
    services = _services(tmp_path)
    services.journal.save_symbol_decision("WATCH", {"decision": "HOLD", "decision_date": "2026-10-01"})
    plan = _propose(services)
    accepted = services.exit_plans.accept(plan["id"], today=TODAY)
    assert accepted["status"] == "ACCEPTED"
    assert services.exit_plans.active("WATCH")["id"] == plan["id"]

    journal = services.journal.symbol_journal("WATCH")
    assert journal["decision"]["decision"] == "HOLD"
    triggers = {row["trigger_type"]: row for row in journal["triggers"]}
    assert set(triggers) == {"PRICE_ABOVE", "PRICE_BELOW", "DATE"}
    assert triggers["PRICE_ABOVE"]["upper_value"] == plan["target_price"]
    assert triggers["PRICE_BELOW"]["lower_value"] == plan["stop_price"]
    assert triggers["DATE"]["trigger_date"] == "2027-02-01"
    assert {row["exit_plan_id"] for row in triggers.values()} == {plan["id"]}

    note = journal["notes"][0]
    assert note["id"] == accepted["note_id"]
    assert (note["author"], note["pinned_date"]) == ("CLAUDE", TODAY.isoformat())
    assert "Exit plan accepted (Claude's proposal)" in note["body"]
    assert plan["reasoning"] in note["body"]

    history = services.journal_repository.decision_history()[0]
    assert (history["previous_decision"], history["new_decision"]) == ("HOLD", "HOLD")
    assert history["claude_disposition"] == "ACCEPTED"

    with pytest.raises(ValueError, match="already accepted"):
        services.exit_plans.accept(plan["id"])
    with pytest.raises(KeyError):
        services.exit_plans.accept("missing")


def test_a_new_accepted_plan_retires_the_old_one_and_rejections_are_kept(tmp_path: Path) -> None:
    services = _services(tmp_path)
    first = _propose(services)
    services.exit_plans.accept(first["id"], today=TODAY)
    rejected = _propose(services, target_price="500")
    services.exit_plans.reject(rejected["id"])
    own = services.exit_plans.create_own(
        "WATCH", target_price="400", stop_price=None, review_date=None, reasoning="My own level.", today=TODAY
    )
    assert (own["status"], own["proposed_by"]) == ("ACCEPTED", "USER")

    statuses = {row["id"]: row["status"] for row in services.exit_plans.plans("WATCH")}
    assert statuses == {first["id"]: "SUPERSEDED", rejected["id"]: "REJECTED", own["id"]: "ACCEPTED"}
    open_triggers = services.journal.symbol_journal("WATCH")["triggers"]
    open_levels = [(row["trigger_type"], row["exit_plan_id"]) for row in open_triggers]
    assert open_levels == [("PRICE_ABOVE", own["id"])]
    old = [row for row in services.journal_repository.triggers() if row["exit_plan_id"] == first["id"]]
    assert {row["state"] for row in old} == {"DISMISSED"}
    # A user's own plan is not a Claude suggestion.
    assert services.journal_repository.decision_history()[0]["claude_disposition"] is None
    assert services.exit_plans.plans(status="PROPOSED") == []
    with pytest.raises(ValueError, match="status"):
        services.exit_plans.plans(status="OPEN")


def test_crossing_an_accepted_level_alerts_with_the_original_reasoning(tmp_path: Path) -> None:
    services = _services(tmp_path)
    plan = _propose(services, target_price=str(LAST_CLOSE - 1), stop_price=str(LAST_CLOSE - 40))
    services.exit_plans.accept(plan["id"], today=TODAY)
    fresh = datetime.combine(LAST_DATE + timedelta(days=1), datetime.min.time(), UTC)
    services.journal.evaluate_triggers(now=fresh)

    alerts = services.journal_repository.alerts()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["exit_plan_id"] == plan["id"]
    assert alert["exit_plan_reasoning"] == plan["reasoning"]
    assert alert["message"] == (
        f"WATCH closed at {LAST_CLOSE}, at or above the exit-plan target of {plan['target_price']}. "
        "Review only; no order was created."
    )
