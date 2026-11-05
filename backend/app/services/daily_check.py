"""Daily review check: refresh prices for tickers with open price triggers, then evaluate them.

Run after the US close. Every due trigger has a local alert; each alert is sent as a desktop
notification once, with the level and the exit plan's reasoning, whether it was found by this
check or earlier by the dashboard. Alerts are reminders to review; nothing here places or
describes an order.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.services.container import Services

PRICE_TRIGGERS = {"PRICE_ABOVE", "PRICE_BELOW", "CONSIDER_ADD_RANGE", "CONSIDER_REDUCE_RANGE"}
REASONING_PREVIEW = 160

Notifier = Callable[[str, str, str], None]
logger = logging.getLogger("investment_tracker.check")


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def macos_notify(title: str, subtitle: str, body: str) -> None:
    """Show a macOS notification through osascript (no extra packages needed)."""
    script = (
        f"display notification {_applescript_string(body)} "
        f"with title {_applescript_string(title)} subtitle {_applescript_string(subtitle)}"
    )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)


def notification_for(alert: dict[str, Any]) -> tuple[str, str, str]:
    body = str(alert["message"])
    reasoning = alert.get("exit_plan_reasoning")
    if reasoning:
        preview = reasoning if len(reasoning) <= REASONING_PREVIEW else f"{reasoning[:REASONING_PREVIEW]}…"
        body = f"{body} Reasoning: {preview}"
    return "Investment Tracker", f"{alert['symbol']} · review due", body


def run_check(
    services: Services,
    *,
    notify: Notifier | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh what the open triggers need, evaluate them, and notify alerts not yet sent."""
    repository = services.journal_repository
    open_triggers = [row for row in repository.triggers() if row["state"] == "ACTIVE"]
    symbols = sorted({str(row["symbol"]) for row in open_triggers if row["trigger_type"] in PRICE_TRIGGERS})

    refreshed: list[str] = []
    failed: dict[str, str] = {}
    for symbol in symbols:
        try:
            _, _, stale = services.market.ensure_history(symbol)
        except Exception as exc:  # one bad ticker shouldn't stop the others
            failed[symbol] = f"{type(exc).__name__}: {exc}"
            continue
        if stale:
            failed[symbol] = "Price history could not be refreshed; the saved copy is stale"
        else:
            refreshed.append(symbol)

    # Held tickers are checked against the latest valuation, so refresh it too.
    if services.portfolio.latest() is not None:
        try:
            services.portfolio.refresh()
        except Exception as exc:
            failed["portfolio"] = f"{type(exc).__name__}: {exc}"

    services.journal.evaluate_triggers(now=now or datetime.now(UTC))
    pending = [alert for alert in repository.alerts() if alert["notified_at"] is None]

    notified = 0
    for alert in pending:
        if notify is None:
            continue
        try:
            notify(*notification_for(alert))
        except Exception as exc:  # left unmarked, so the next run tries again
            logger.warning("Notification failed for %s: %s", alert["symbol"], exc)
            continue
        repository.mark_alert_notified(alert["id"])
        notified += 1

    return {
        "checked_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "open_triggers": len(open_triggers),
        "refreshed": refreshed,
        "failed": failed,
        "due_alerts": pending,
        "notified": notified,
    }
