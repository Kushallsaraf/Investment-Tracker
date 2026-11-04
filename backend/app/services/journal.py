"""Local decisions, conviction notes, and review-only triggers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.journal_repository import JournalRepository
from app.providers.prices import normalize_symbol
from app.repository import PortfolioRepository

DECISIONS = {"WATCH", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "EXIT_CANDIDATE"}
ROLES = {"CORE", "DIVERSIFIER", "INCOME", "SPECULATIVE"}
CLAUDE_SUGGESTIONS = {
    "CONSIDER_BUY",
    "HOLD",
    "CONSIDER_REDUCE",
    "CONSIDER_EXIT",
    "INSUFFICIENT_DATA",
}
DISPOSITIONS = {"ACCEPTED", "REJECTED", "CONSIDERING"}
NOTE_AUTHORS = {"USER", "CLAUDE"}
MAX_NOTE_LENGTH = 10_000
# A daily close older than this is too stale to fire a price trigger for an unheld ticker.
MAX_CLOSE_AGE = timedelta(days=5)
TRIGGER_TYPES = {
    "PRICE_BELOW",
    "PRICE_ABOVE",
    "CONSIDER_ADD_RANGE",
    "CONSIDER_REDUCE_RANGE",
    "DATE",
    "AFTER_EARNINGS",
    "THESIS_NOTE",
}


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class JournalService:
    def __init__(
        self,
        repository: JournalRepository,
        portfolio_repository: PortfolioRepository,
        *,
        market: Any = None,
    ) -> None:
        self.repository = repository
        self.portfolio_repository = portfolio_repository
        # The market service is optional: it resolves Terminal tickers that are not held
        # and supplies cached daily closes for their price triggers.
        self.market = market

    def _instrument(self, instrument_id: str) -> dict[str, Any]:
        instrument = self.portfolio_repository.instrument(instrument_id)
        if instrument is None:
            raise KeyError("Instrument was not found")
        return instrument

    def resolve_symbol(self, symbol: str) -> str:
        """Instrument ID for any Terminal ticker, created from its cached listing if not held."""
        canonical = normalize_symbol(symbol)
        existing = self.portfolio_repository.instrument_by_symbol(canonical)
        if existing is not None:
            return str(existing["id"])
        if self.market is None:
            raise KeyError(f"{canonical} has no instrument record")
        meta, _, _ = self.market.ensure_history(canonical)
        return self.portfolio_repository.ensure_instrument(
            {
                "canonical_symbol": meta["symbol"],
                "security_name": meta["security_name"],
                "asset_type": meta["asset_type"],
                "exchange": meta["exchange"],
            }
        )

    def symbol_journal(self, symbol: str) -> dict[str, Any]:
        """Decision, open triggers, and notes for one ticker, held or not."""
        canonical = normalize_symbol(symbol)
        self.evaluate_triggers()
        instrument = self.portfolio_repository.instrument_by_symbol(canonical)
        instrument_id = str(instrument["id"]) if instrument else None
        decision = next(
            (row for row in self.repository.decisions() if row["instrument_id"] == instrument_id),
            None,
        )
        open_states = {"ACTIVE", "TRIGGERED"}
        triggers = (
            [row for row in self.repository.triggers(instrument_id) if row["state"] in open_states]
            if instrument_id
            else []
        )
        return {
            "symbol": canonical,
            "instrument_id": instrument_id,
            "decision": decision,
            "triggers": triggers,
            "notes": self.repository.notes(canonical),
            "exit_plans": self.repository.exit_plans(canonical),
        }

    def save_symbol_decision(self, symbol: str, values: dict[str, Any]) -> dict[str, Any]:
        return self.save_decision(self.resolve_symbol(symbol), values)

    @staticmethod
    def _note_values(body: str, pinned_date: str | None) -> tuple[str, str | None]:
        text = body.strip()
        if not text:
            raise ValueError("A note needs some text")
        if len(text) > MAX_NOTE_LENGTH:
            raise ValueError(f"Notes are limited to {MAX_NOTE_LENGTH:,} characters")
        pinned = None
        if pinned_date:
            parsed = _date(pinned_date)
            if parsed is None or len(pinned_date) != 10:
                raise ValueError("Pinned date must be an ISO date")
            if parsed > datetime.now(UTC).date():
                raise ValueError("Pinned date can't be in the future")
            pinned = parsed.isoformat()
        return text, pinned

    def add_note(
        self, symbol: str, body: str, pinned_date: str | None = None, *, author: str = "USER"
    ) -> dict[str, Any]:
        if author not in NOTE_AUTHORS:
            raise ValueError("Unsupported note author")
        text, pinned = self._note_values(body, pinned_date)
        return self.repository.add_note(normalize_symbol(symbol), text, pinned, author)

    def update_note(self, note_id: str, body: str, pinned_date: str | None = None) -> dict[str, Any]:
        text, pinned = self._note_values(body, pinned_date)
        return self.repository.update_note(note_id, text, pinned)

    def delete_note(self, note_id: str) -> None:
        self.repository.delete_note(note_id)

    def save_profile(self, instrument_id: str, values: dict[str, Any]) -> dict[str, Any]:
        holding = self._instrument(instrument_id)
        role = values.get("portfolio_role")
        strength = values.get("thesis_strength")
        maximum = _decimal(values.get("maximum_weight"))
        if role is not None and role not in ROLES:
            raise ValueError("Unsupported portfolio role")
        if strength is not None and (not isinstance(strength, int) or not 1 <= strength <= 5):
            raise ValueError("Thesis strength must be between 1 and 5")
        if maximum is not None and not Decimal("0") <= maximum <= Decimal("1"):
            raise ValueError("Maximum portfolio weight must be between 0 and 1")
        normalized = {
            **values,
            "maximum_weight": format(maximum, "f") if maximum is not None else None,
        }
        self.repository.save_profile(
            instrument_id, str(holding["canonical_symbol"]), normalized
        )
        return self.repository.profile(instrument_id) or {}

    def save_decision(self, instrument_id: str, values: dict[str, Any]) -> dict[str, Any]:
        holding = self._instrument(instrument_id)
        decision = str(values.get("decision") or "")
        if decision not in DECISIONS:
            raise ValueError("Unsupported investment decision")
        disposition = values.get("claude_disposition")
        if disposition is not None and disposition not in DISPOSITIONS:
            raise ValueError("Unsupported Claude suggestion status")
        return self.repository.save_decision(
            instrument_id, str(holding["canonical_symbol"]), values
        )

    def create_trigger(self, instrument_id: str, values: dict[str, Any]) -> dict[str, Any]:
        holding = self._instrument(instrument_id)
        trigger_type = str(values.get("trigger_type") or "")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError("Unsupported review trigger")
        lower = _decimal(values.get("lower_value"))
        upper = _decimal(values.get("upper_value"))
        if trigger_type == "PRICE_BELOW" and lower is None:
            raise ValueError("Review-below triggers require a price")
        if trigger_type == "PRICE_ABOVE" and upper is None:
            raise ValueError("Review-above triggers require a price")
        if trigger_type in {"CONSIDER_ADD_RANGE", "CONSIDER_REDUCE_RANGE"}:
            if lower is None or upper is None or lower > upper:
                raise ValueError("Price ranges require valid lower and upper values")
        if trigger_type in {"DATE", "AFTER_EARNINGS"} and _date(values.get("trigger_date")) is None:
            raise ValueError("This review trigger requires a date")
        normalized = {
            **values,
            "lower_value": format(lower, "f") if lower is not None else None,
            "upper_value": format(upper, "f") if upper is not None else None,
        }
        created = self.repository.create_trigger(
            instrument_id, str(holding["canonical_symbol"]), normalized
        )
        self.evaluate_triggers()
        return created

    def _daily_close(self, symbol: str, now: datetime) -> dict[str, Any] | None:
        """Latest cached daily close for a ticker that is not in the portfolio."""
        if self.market is None:
            return None
        bars = self.market.repository.bars(symbol)
        if not bars:
            return None
        last = bars[-1]
        stale = now.date() - date.fromisoformat(last["date"]) > MAX_CLOSE_AGE
        return {
            "price": str(last["close"]),
            "price_stale": stale,
            "data_status": "stale" if stale else "end_of_day",
            "price_source": "Yahoo Finance chart (daily close)",
            "price_timestamp": last["date"],
        }

    def evaluate_triggers(self, now: datetime | None = None) -> None:
        effective_now = now or datetime.now(UTC)
        portfolio = self.portfolio_repository.latest_portfolio() or {
            "holdings": [],
            "holding_snapshot_id": None,
            "valuation_snapshot_id": None,
        }
        holdings = {row["instrument_id"]: row for row in portfolio["holdings"]}
        for trigger in self.repository.triggers():
            if trigger["state"] != "ACTIVE":
                continue
            expiry = _date(trigger.get("expires_at"))
            if expiry and expiry < effective_now.date():
                self.repository.expire_trigger(trigger["id"])
                continue
            holding = holdings.get(trigger["instrument_id"])
            trigger_type = trigger["trigger_type"]
            due = False
            observed_value: str | None = None
            if trigger_type in {"DATE", "AFTER_EARNINGS"}:
                due_date = _date(trigger.get("trigger_date"))
                due = bool(due_date and due_date <= effective_now.date())
            elif trigger_type != "THESIS_NOTE":
                if holding is None:
                    holding = self._daily_close(str(trigger["symbol"]), effective_now)
                if holding is None:
                    continue
                price = _decimal(holding.get("price"))
                sufficiently_fresh = bool(
                    price is not None
                    and not holding.get("price_stale")
                    and "stale" not in str(holding.get("data_status") or "").lower()
                )
                if sufficiently_fresh and price is not None:
                    observed_value = format(price, "f")
                    lower = _decimal(trigger.get("lower_value"))
                    upper = _decimal(trigger.get("upper_value"))
                    if trigger_type == "PRICE_BELOW":
                        due = bool(lower is not None and price <= lower)
                    elif trigger_type == "PRICE_ABOVE":
                        due = bool(upper is not None and price >= upper)
                    else:
                        due = bool(lower is not None and upper is not None and lower <= price <= upper)
            if due:
                self.repository.trigger(
                    trigger["id"],
                    {
                        "observed_value": observed_value,
                        "quote_source": holding.get("price_source") if holding else None,
                        "quote_timestamp": holding.get("price_timestamp") if holding else None,
                        "holding_snapshot_id": portfolio["holding_snapshot_id"],
                        "valuation_snapshot_id": portfolio["valuation_snapshot_id"],
                    },
                )

    def overview(self) -> dict[str, Any]:
        self.evaluate_triggers()
        portfolio = self.portfolio_repository.latest_portfolio()
        holdings = (portfolio or {}).get("holdings", [])
        profiles = {row["instrument_id"]: row for row in self.repository.profiles()}
        decisions = {row["instrument_id"]: row for row in self.repository.decisions()}
        reviews = self.repository.ai_reviews()
        latest_review: dict[str, dict[str, Any]] = {}
        for review in reviews:
            latest_review.setdefault(review["instrument_id"], review)
        triggers = self.repository.triggers()
        active_by_instrument: dict[str, dict[str, Any]] = {}
        for trigger in triggers:
            if trigger["state"] in {"TRIGGERED", "ACTIVE"}:
                active_by_instrument.setdefault(trigger["instrument_id"], trigger)
        return {
            "entries": [
                {
                    "holding": row,
                    "profile": profiles.get(row["instrument_id"]),
                    "decision": decisions.get(row["instrument_id"]),
                    "latest_ai_review": latest_review.get(row["instrument_id"]),
                    "active_trigger": active_by_instrument.get(row["instrument_id"]),
                }
                for row in holdings
            ],
            "decision_history": self.repository.decision_history(),
            "triggers": triggers,
            "alerts": self.repository.alerts(),
            "generated_at": datetime.now(UTC).isoformat(),
        }
