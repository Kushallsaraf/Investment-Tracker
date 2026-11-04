"""Exit plans: target, stop, and review date for a ticker, proposed by Claude or the investor.

A proposal is only a suggestion. Accepting one (from the dashboard, never from Claude) turns it
into review-only triggers, a dated note, and a decision-history entry; the investor's decision
itself is left unchanged. Nothing here creates, simulates, or describes an order.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.journal_repository import JournalRepository
from app.providers.prices import normalize_symbol
from app.services.journal import MAX_NOTE_LENGTH, JournalService, _decimal

PROPOSERS = {"CLAUDE", "USER"}
STATUSES = {"PROPOSED", "ACCEPTED", "REJECTED", "SUPERSEDED"}


def _price(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    parsed = _decimal(value)
    if parsed is None or parsed <= 0:
        raise ValueError(f"{label} must be a positive price")
    return format(parsed.quantize(Decimal("0.01")), "f")


class ExitPlanService:
    def __init__(self, repository: JournalRepository, journal: JournalService) -> None:
        self.repository = repository
        self.journal = journal

    def _reference(self, symbol: str) -> tuple[str | None, str | None]:
        """Latest cached daily close, so a proposal records the price it was made against."""
        market = self.journal.market
        if market is None:
            return None, None
        _, bars, _ = market.ensure_history(symbol)
        if not bars:
            return None, None
        close = Decimal(str(bars[-1]["close"])).quantize(Decimal("0.01"))
        return format(close, "f"), str(bars[-1]["date"])

    def propose(
        self,
        symbol: str,
        *,
        target_price: Any = None,
        stop_price: Any = None,
        review_date: str | None = None,
        reasoning: str,
        proposed_by: str = "CLAUDE",
        today: date | None = None,
    ) -> dict[str, Any]:
        if proposed_by not in PROPOSERS:
            raise ValueError("Unsupported exit plan author")
        canonical = normalize_symbol(symbol)
        target = _price(target_price, "Target")
        stop = _price(stop_price, "Stop")
        if target is None and stop is None and not review_date:
            raise ValueError("An exit plan needs a target, a stop, or a review date")
        if target is not None and stop is not None and Decimal(target) <= Decimal(stop):
            raise ValueError("The target must be above the stop")
        review = None
        if review_date:
            try:
                parsed = date.fromisoformat(review_date)
            except ValueError:
                raise ValueError("Review date must be an ISO date (YYYY-MM-DD)") from None
            if parsed < (today or datetime.now(UTC).date()):
                raise ValueError("Review date can't be in the past")
            review = parsed.isoformat()
        text = (reasoning or "").strip()
        if not text:
            raise ValueError("An exit plan needs its reasoning")
        if len(text) > MAX_NOTE_LENGTH:
            raise ValueError(f"Reasoning is limited to {MAX_NOTE_LENGTH:,} characters")
        # Resolving the ticker validates it and gives accepted triggers an instrument to hang on.
        self.journal.resolve_symbol(canonical)
        reference_price, reference_date = self._reference(canonical)
        return self.repository.add_exit_plan(
            {
                "symbol": canonical,
                "target_price": target,
                "stop_price": stop,
                "review_date": review,
                "reasoning": text,
                "proposed_by": proposed_by,
                "reference_price": reference_price,
                "reference_date": reference_date,
            }
        )

    def create_own(self, symbol: str, **values: Any) -> dict[str, Any]:
        """A plan the investor writes is accepted as soon as it is saved."""
        plan = self.propose(symbol, proposed_by="USER", **values)
        return self.accept(plan["id"])

    def plans(self, symbol: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise ValueError("Unsupported exit plan status")
        return self.repository.exit_plans(normalize_symbol(symbol) if symbol else None, status)

    def active(self, symbol: str) -> dict[str, Any] | None:
        accepted = self.repository.exit_plans(normalize_symbol(symbol), "ACCEPTED")
        return accepted[0] if accepted else None

    def _open_plan(self, plan_id: str) -> dict[str, Any]:
        plan = self.repository.exit_plan(plan_id)
        if plan is None:
            raise KeyError("Exit plan was not found")
        if plan["status"] != "PROPOSED":
            raise ValueError(f"This exit plan is already {str(plan['status']).lower()}")
        return plan

    def accept(self, plan_id: str, today: date | None = None) -> dict[str, Any]:
        plan = self._open_plan(plan_id)
        symbol = str(plan["symbol"])
        instrument_id = self.journal.resolve_symbol(symbol)
        on = (today or datetime.now(UTC).date()).isoformat()

        levels = [
            f"target {plan['target_price']}" if plan["target_price"] else None,
            f"stop {plan['stop_price']}" if plan["stop_price"] else None,
            f"review on {plan['review_date']}" if plan["review_date"] else None,
        ]
        summary = ", ".join(item for item in levels if item)
        author = "Claude's" if plan["proposed_by"] == "CLAUDE" else "My"
        note = self.journal.add_note(
            symbol,
            f"Exit plan accepted ({author} proposal): {summary}.\n\n{plan['reasoning']}",
            on,
            author=str(plan["proposed_by"]),
        )
        accepted = self.repository.decide_exit_plan(plan_id, "ACCEPTED", note_id=str(note["id"]))

        reason = f"Exit plan: {plan['reasoning']}"
        triggers: list[dict[str, Any]] = []
        if plan["target_price"]:
            triggers.append({"trigger_type": "PRICE_ABOVE", "upper_value": plan["target_price"]})
        if plan["stop_price"]:
            triggers.append({"trigger_type": "PRICE_BELOW", "lower_value": plan["stop_price"]})
        if plan["review_date"]:
            triggers.append({"trigger_type": "DATE", "trigger_date": plan["review_date"]})
        for values in triggers:
            self.journal.create_trigger(
                instrument_id,
                {**values, "reason": reason, "note": summary, "exit_plan_id": plan_id},
            )

        # Record the acceptance in decision history without changing the decision itself.
        current = next(
            (row for row in self.repository.decisions() if row["instrument_id"] == instrument_id),
            None,
        )
        self.journal.save_decision(
            instrument_id,
            {
                "decision": current["decision"] if current else "WATCH",
                "decision_date": on,
                "reason": f"Accepted exit plan: {summary}",
                "claude_disposition": "ACCEPTED" if plan["proposed_by"] == "CLAUDE" else None,
                "review_due_date": plan["review_date"] or (current or {}).get("review_due_date"),
            },
        )
        return accepted

    def reject(self, plan_id: str) -> dict[str, Any]:
        self._open_plan(plan_id)
        return self.repository.decide_exit_plan(plan_id, "REJECTED")
