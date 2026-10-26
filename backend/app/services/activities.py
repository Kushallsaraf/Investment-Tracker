"""Normalization and read models for completed, daily brokerage activities."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.repository import PortfolioRepository

SUPPORTED_ACTIVITY_TYPES = {
    "BUY": "BUY",
    "SELL": "SELL",
    "DIVIDEND": "DISTRIBUTION",
    "SUBSTITUTE_DIVIDEND": "DISTRIBUTION",
    "REI": "DISTRIBUTION",
    "STOCK_DIVIDEND": "DISTRIBUTION",
    "CONTRIBUTION": "DEPOSIT",
    "DEPOSIT": "DEPOSIT",
    "WITHDRAWAL": "WITHDRAWAL",
    "FEE": "FEE",
    "INTEREST": "INTEREST",
    "TAX": "WITHHOLDING_TAX",
    "WITHHOLDING_TAX": "WITHHOLDING_TAX",
    "TRANSFER": "TRANSFER",
}
SECURITY_ACTIVITY_TYPES = {"BUY", "SELL", "DISTRIBUTION"}
_SAFE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9./-]{0,31}$")


def _decimal_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return format(parsed, "f") if parsed.is_finite() else None


def _date_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _currency(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("code") or value.get("currency")
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"CAD", "USD"} else None


def _symbol(value: Any) -> str | None:
    """Extract only a confidently supplied canonical/raw symbol; never guess an exchange."""
    if not isinstance(value, dict):
        return None
    raw: Any = value.get("symbol") or value.get("raw_symbol")
    if isinstance(raw, dict):
        raw = raw.get("symbol") or raw.get("raw_symbol")
    normalized = str(raw or "").strip().upper()
    if not normalized:
        return None
    exchange = value.get("exchange") or {}
    suffix = str(exchange.get("suffix") or "").strip().upper() if isinstance(exchange, dict) else ""
    if suffix in {".TO", ".V"} and not normalized.endswith((".TO", ".V")):
        normalized = f"{normalized}{suffix}"
    return normalized if _SAFE_SYMBOL.fullmatch(normalized) else None


def normalize_snaptrade_activity(
    activity: dict[str, Any],
    *,
    account_fingerprint: str,
    local_secret: bytes,
    source_as_of: str | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Normalize one synthetic or live response without retaining raw identifiers/payloads."""
    warnings: list[dict[str, str]] = []
    raw_type = str(activity.get("type") or "").strip().upper()[:64]
    normalized_type = SUPPORTED_ACTIVITY_TYPES.get(raw_type, "OTHER")
    if normalized_type == "OTHER":
        warnings.append(
            {
                "code": "UNSUPPORTED_ACTIVITY_TYPE",
                "message": f"Activity type {raw_type or 'missing'} was stored as OTHER.",
            }
        )
    symbol = _symbol(activity.get("symbol"))
    if normalized_type in SECURITY_ACTIVITY_TYPES and symbol is None:
        warnings.append(
            {
                "code": "MISSING_ACTIVITY_SYMBOL",
                "message": f"A {normalized_type.lower()} activity has no resolved symbol.",
            }
        )
    trade_date = _date_time(activity.get("trade_date"))
    if trade_date is None:
        warnings.append(
            {
                "code": "MISSING_ACTIVITY_DATE",
                "message": "An activity has no usable trade date.",
            }
        )
    external_id = str(activity.get("id") or "").strip()
    if not external_id:
        external_id = json.dumps(
            {
                "type": raw_type,
                "symbol": symbol,
                "trade_date": trade_date,
                "units": activity.get("units"),
                "price": activity.get("price"),
                "amount": activity.get("amount"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        warnings.append(
            {
                "code": "MISSING_ACTIVITY_ID",
                "message": "A deterministic local identity was derived because the activity ID was missing.",
            }
        )
    activity_key = hmac.new(
        local_secret,
        f"snaptrade-activity:{account_fingerprint}:{external_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    normalized = {
        "activity_key": activity_key,
        "account_fingerprint": account_fingerprint,
        "normalized_type": normalized_type,
        "symbol": symbol,
        "trade_date": trade_date,
        "settlement_date": _date_time(activity.get("settlement_date")),
        "quantity": _decimal_text(activity.get("units")),
        "price": _decimal_text(activity.get("price")),
        "currency": _currency(activity.get("currency")),
        "fee": _decimal_text(activity.get("fee")),
        "cash_amount": _decimal_text(activity.get("amount")),
        "source_as_of": source_as_of,
    }
    canonical = json.dumps(
        {
            key: value
            for key, value in normalized.items()
            if key not in {"account_fingerprint", "source_as_of"}
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    normalized["record_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return normalized, warnings


def summarize_activity_preview(
    rows: list[dict[str, Any]],
    stored_hashes: dict[str, str],
    *,
    accounts: list[dict[str, Any]],
    unsupported_activity_types: set[str],
    incomplete: bool,
) -> dict[str, Any]:
    additions = sum(row["activity_key"] not in stored_hashes for row in rows)
    changed = sum(
        row["activity_key"] in stored_hashes
        and stored_hashes[row["activity_key"]] != row["record_hash"]
        for row in rows
    )
    dates = sorted(row["trade_date"] for row in rows if row.get("trade_date"))
    type_counts = dict(sorted(Counter(row["normalized_type"] for row in rows).items()))
    missing_symbols = sorted(
        {
            f"{row['normalized_type']} · {row.get('trade_date') or 'MISSING DATE'}"
            for row in rows
            if row["normalized_type"] in SECURITY_ACTIVITY_TYPES and not row.get("symbol")
        }
    )
    return {
        "additions": additions,
        "changed_records": changed,
        "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
        "type_counts": type_counts,
        "missing_symbols": missing_symbols,
        "unsupported_activity_types": sorted(unsupported_activity_types),
        "coverage_start": dates[0] if dates else None,
        "coverage_end": dates[-1] if dates else None,
        "incomplete_initial_sync": incomplete,
        "warning": (
            "Transaction history may be incomplete; SnapTrade has not returned every available page."
            if incomplete
            else None
        ),
        "accounts": accounts,
    }


class ActivityService:
    """Read normalized local activities and compute evidence-backed income summaries."""

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

    def income(self, now: datetime | None = None) -> dict[str, Any]:
        effective_now = now or datetime.now(UTC)
        start = effective_now - timedelta(days=365)
        payload = self.repository.activities_view(
            start_date=start.isoformat(), end_date=effective_now.isoformat(), limit=5_000
        )
        rows = payload["activities"]
        income_types = {"DISTRIBUTION", "INTEREST"}
        received_by_currency: dict[str, Decimal] = {}
        tax_by_currency: dict[str, Decimal] = {}
        by_holding: dict[str, dict[str, Decimal]] = {}
        for row in rows:
            amount = _decimal_text(row.get("cash_amount"))
            value = Decimal(amount) if amount is not None else None
            currency = row.get("currency")
            if value is None or currency not in {"CAD", "USD"}:
                continue
            if row["normalized_type"] in income_types:
                received_by_currency[currency] = received_by_currency.get(currency, Decimal("0")) + value
                holding = row.get("symbol") or "CASH"
                bucket = by_holding.setdefault(holding, {})
                bucket[currency] = bucket.get(currency, Decimal("0")) + value
            elif row["normalized_type"] == "WITHHOLDING_TAX":
                tax_by_currency[currency] = tax_by_currency.get(currency, Decimal("0")) + abs(value)
        warnings = list(payload["warnings"])
        if not payload["coverage"]["complete"]:
            warnings.append("Income may be incomplete because brokerage activity coverage is incomplete.")
        if any(currency != "CAD" for currency in received_by_currency):
            warnings.append(
                "Non-CAD income remains in its source currency because activity-date FX "
                "conversion evidence is unavailable."
            )
        return {
            "period_start": start.isoformat(),
            "period_end": effective_now.isoformat(),
            "source": "SnapTrade daily completed activities",
            "source_as_of": payload["coverage"].get("source_as_of"),
            "received_by_currency": {key: format(value, "f") for key, value in received_by_currency.items()},
            "withholding_tax_by_currency": {
                key: format(value, "f") for key, value in tax_by_currency.items()
            },
            "income_by_holding": [
                {"symbol": symbol, "amounts": {key: format(value, "f") for key, value in values.items()}}
                for symbol, values in sorted(by_holding.items())
            ],
            "forward_annual_estimate": None,
            "portfolio_yield": None,
            "upcoming_distributions": [],
            "coverage": payload["coverage"],
            "warnings": list(dict.fromkeys(warnings)),
        }
