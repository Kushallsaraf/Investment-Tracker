"""Manual holdings maintenance, price retrieval, and deterministic USD portfolio valuation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.prices import PriceProvider, YahooDailyPriceProvider
from app.repository import PortfolioRepository
from app.services.demo import demo_activities, demo_positions

CASH_IDENTITY = {
    "canonical_symbol": "USD",
    "security_name": "US dollar cash",
    "asset_type": "CASH",
    "exchange": "CASH",
}
CASH_SYMBOLS = {"CASH", "USD", "$"}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


class PortfolioService:
    def __init__(
        self,
        repository: PortfolioRepository | None = None,
        *,
        price_provider: PriceProvider | None = None,
    ) -> None:
        self.repository = repository or PortfolioRepository()
        self.price_provider = price_provider or YahooDailyPriceProvider()

    def refresh(self, holding_snapshot_id: str | None = None) -> str:
        snapshot_id = holding_snapshot_id or self.repository.latest_holding_snapshot_id()
        if snapshot_id is None:
            raise ValueError("No holdings snapshot exists")
        positions = self.repository.positions_for_snapshot(snapshot_id)
        warnings: list[str] = []

        quotes: dict[str, tuple[str, dict[str, Any]] | None] = {}
        for position in positions:
            instrument_id = str(position["instrument_id"])
            if instrument_id in quotes:
                continue
            try:
                if position["asset_type"] == "CASH":
                    fetched_at = datetime.now(UTC).isoformat()
                    quote = {
                        "price": "1",
                        "observed_at": fetched_at,
                        "fetched_at": fetched_at,
                        "source": "Currency face value",
                        "source_url": None,
                        "quote_status": "not_applicable",
                        "delay_minutes": None,
                        "stale": False,
                    }
                else:
                    quote = self.price_provider.quote(position)
                quote_id = self.repository.save_quote(instrument_id, quote)
                quotes[instrument_id] = (quote_id, quote)
            except Exception as exc:
                quotes[instrument_id] = None
                warnings.append(
                    f"{position['canonical_symbol']}: latest price unavailable ({type(exc).__name__})."
                )

        valued: list[dict[str, Any]] = []
        total = Decimal("0")
        priced = 0
        for position in positions:
            quote_entry = quotes.get(str(position["instrument_id"]))
            quote_id: str | None = None
            price: Decimal | None = None
            data_status = "missing"
            if quote_entry is not None:
                quote_id, quote = quote_entry
                data_status = "stale" if quote["stale"] else str(quote["quote_status"])
                price = _decimal(quote.get("price"))

            quantity = _decimal(position["quantity"]) or Decimal("0")
            market_value = quantity * price if price is not None else None
            average_cost = _decimal(position.get("average_cost"))
            gain = (
                (price - average_cost) * quantity
                if price is not None and average_cost is not None and position["asset_type"] != "CASH"
                else None
            )
            if market_value is not None:
                total += market_value
                priced += 1
            valued.append(
                {
                    **position,
                    "price_quote_id": quote_id,
                    "market_value": _text(market_value),
                    "unrealized_gain_loss": _text(gain),
                    "portfolio_weight": None,
                    "data_status": data_status,
                }
            )

        if total > 0:
            for row in valued:
                market_value = _decimal(row["market_value"])
                if market_value is not None:
                    row["portfolio_weight"] = _text(market_value / total)
        total_positions = len(positions)
        coverage = Decimal(priced) / Decimal(total_positions) if total_positions else Decimal("0")
        if priced != total_positions:
            warnings.append(
                f"Only {priced} of {total_positions} positions are included in the total; "
                "weights are relative to priced positions only."
            )
        return self.repository.save_valuation(
            holding_snapshot_id=snapshot_id,
            total_value=_text(total) or "0",
            priced_positions=priced,
            total_positions=total_positions,
            coverage_pct=_text(coverage) or "0",
            warnings=list(dict.fromkeys(warnings)),
            positions=valued,
        )

    def latest(self) -> dict[str, Any] | None:
        return self.repository.latest_portfolio()

    def status(self) -> dict[str, Any]:
        latest = self.repository.latest_snapshot()
        return {
            "data_origin": latest["data_origin"] if latest else None,
            "snapshot_count": self.repository.snapshot_count(),
            "latest_snapshot_at": latest["created_at"] if latest else None,
        }

    def price_capabilities(self) -> dict[str, Any]:
        supported = bool(getattr(self.price_provider, "supports_automatic_refresh", False))
        interval = getattr(self.price_provider, "automatic_refresh_seconds", None)
        safe_interval = max(30, min(60, int(interval))) if supported and interval else None
        return {
            "provider": str(getattr(self.price_provider, "source", type(self.price_provider).__name__)),
            "automatic_refresh_supported": supported,
            "automatic_refresh_seconds": safe_interval,
        }

    def upsert_position(
        self,
        *,
        symbol: str,
        quantity: str,
        average_cost: str | None,
        account_name: str,
    ) -> dict[str, str]:
        parsed_quantity = _decimal(quantity)
        if parsed_quantity is None or parsed_quantity <= 0:
            raise ValueError("Quantity must be a positive number")
        parsed_cost = _decimal(average_cost) if average_cost not in (None, "") else None
        if average_cost not in (None, "") and (parsed_cost is None or parsed_cost < 0):
            raise ValueError("Average cost must be a non-negative number")
        account = account_name.strip() or "Brokerage"
        if symbol.strip().upper() in CASH_SYMBOLS:
            identity = dict(CASH_IDENTITY)
            parsed_cost = Decimal("1")
        else:
            identity = self.price_provider.lookup(symbol)
        row = {
            **identity,
            "account_name": account,
            "quantity": _text(parsed_quantity),
            "average_cost": _text(parsed_cost),
        }
        snapshot_id = self.repository.create_snapshot_with_position(row)
        return {
            "holding_snapshot_id": snapshot_id,
            "valuation_snapshot_id": self.refresh(snapshot_id),
            "symbol": identity["canonical_symbol"],
        }

    def remove_position(self, position_id: str) -> dict[str, str]:
        holding_snapshot_id, symbol = self.repository.create_snapshot_without_position(position_id)
        valuation_snapshot_id = self.refresh(holding_snapshot_id)
        return {
            "holding_snapshot_id": holding_snapshot_id,
            "valuation_snapshot_id": valuation_snapshot_id,
            "removed_symbol": symbol,
        }

    def load_demo(self, today: datetime | None = None) -> dict[str, str]:
        latest = self.repository.latest_snapshot()
        manual_holdings = latest is not None and latest["data_origin"] != "demo"
        if manual_holdings or self.repository.activity_count("manual"):
            raise ValueError("Delete local portfolio data before loading the demo portfolio")
        self.repository.delete_portfolio_data()
        snapshot_id = self.repository.create_snapshot(
            demo_positions(), source_type="demo", data_origin="demo"
        )
        for activity in demo_activities((today or datetime.now(UTC)).date()):
            self.repository.add_activity(activity, data_origin="demo")
        return {"holding_snapshot_id": snapshot_id, "valuation_snapshot_id": self.refresh(snapshot_id)}

    def delete_data(self) -> int:
        return self.repository.delete_portfolio_data()

    def history(self, limit: int = 180) -> list[dict[str, Any]]:
        return self.repository.portfolio_history(limit)
