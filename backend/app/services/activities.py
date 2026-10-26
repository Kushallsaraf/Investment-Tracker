"""Manual activity ledger and evidence-backed income summaries (USD)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.prices import UnsupportedSymbolError, normalize_symbol
from app.repository import PortfolioRepository

SECURITY_ACTIVITY_TYPES = {"BUY", "SELL", "DIVIDEND"}
INCOME_TYPES = {"DIVIDEND", "INTEREST"}


def _decimal_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{value!r} is not a number") from exc
    if not parsed.is_finite():
        raise ValueError(f"{value!r} is not a finite number")
    return format(parsed, "f")


class ActivityService:
    """Record manual activities and compute income from them."""

    def __init__(self, repository: PortfolioRepository | None = None) -> None:
        self.repository = repository or PortfolioRepository()

    def list(
        self,
        *,
        activity_type: str | None = None,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        return self.repository.activities_view(
            activity_type=activity_type,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def record(self, values: dict[str, Any]) -> str:
        activity_type = str(values.get("activity_type") or "").upper()
        raw_symbol = str(values.get("symbol") or "").strip()
        try:
            symbol = normalize_symbol(raw_symbol) if raw_symbol else None
        except UnsupportedSymbolError as exc:
            raise ValueError(str(exc)) from exc
        if activity_type in SECURITY_ACTIVITY_TYPES and symbol is None:
            raise ValueError(f"A {activity_type.lower()} activity needs a symbol")
        trade_date = values.get("trade_date")
        try:
            parsed_date = date.fromisoformat(str(trade_date))
        except ValueError as exc:
            raise ValueError("Trade date must be an ISO date") from exc
        normalized = {
            "activity_type": activity_type,
            "symbol": symbol,
            "trade_date": parsed_date.isoformat(),
            "quantity": _decimal_text(values.get("quantity")),
            "price": _decimal_text(values.get("price")),
            "fee": _decimal_text(values.get("fee")),
            "cash_amount": _decimal_text(values.get("cash_amount")),
            "note": str(values.get("note") or "")[:2_000],
        }
        if normalized["cash_amount"] is None and activity_type not in {"BUY", "SELL"}:
            raise ValueError("Cash amount is required for this activity type")
        return self.repository.add_activity(normalized)

    def delete(self, activity_id: str) -> None:
        self.repository.delete_activity(activity_id)

    def income(self, now: datetime | None = None) -> dict[str, Any]:
        effective_now = now or datetime.now(UTC)
        start = effective_now - timedelta(days=365)
        payload = self.repository.activities_view(
            start_date=start.date().isoformat(), end_date=effective_now.date().isoformat(), limit=5_000
        )
        received = Decimal("0")
        withholding = Decimal("0")
        by_holding: dict[str, Decimal] = {}
        for row in payload["activities"]:
            if row.get("cash_amount") is None:
                continue
            value = Decimal(str(row["cash_amount"]))
            if row["activity_type"] in INCOME_TYPES:
                received += value
                holding = row.get("symbol") or "CASH"
                by_holding[holding] = by_holding.get(holding, Decimal("0")) + value
            elif row["activity_type"] == "WITHHOLDING_TAX":
                withholding += abs(value)
        warnings = list(payload["warnings"])
        warnings.append("Income is calculated only from activities recorded in this application.")
        return {
            "period_start": start.isoformat(),
            "period_end": effective_now.isoformat(),
            "source": payload["source"],
            "received": format(received, "f"),
            "withholding_tax": format(withholding, "f"),
            "income_by_holding": [
                {"symbol": symbol, "amount": format(value, "f")}
                for symbol, value in sorted(by_holding.items())
            ],
            "forward_annual_estimate": None,
            "portfolio_yield": None,
            "upcoming_distributions": [],
            "coverage": payload["coverage"],
            "warnings": list(dict.fromkeys(warnings)),
        }
