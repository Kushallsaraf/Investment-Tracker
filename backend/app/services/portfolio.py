"""Price retrieval and deterministic CAD portfolio valuation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.fx import BankOfCanadaFxProvider, FxProvider
from app.providers.prices import PriceProvider, YahooDailyPriceProvider
from app.repository import PortfolioRepository


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
        fx_provider: FxProvider | None = None,
    ) -> None:
        self.repository = repository or PortfolioRepository()
        self.price_provider = price_provider or YahooDailyPriceProvider()
        self.fx_provider = fx_provider or BankOfCanadaFxProvider()

    def refresh(self, holding_snapshot_id: str | None = None) -> str:
        snapshot_id = holding_snapshot_id or self.repository.latest_holding_snapshot_id()
        if snapshot_id is None:
            raise ValueError("No accepted holdings snapshot exists")
        positions = self.repository.positions_for_snapshot(snapshot_id)
        warnings: list[str] = []

        usd_positions = any(row["trading_currency"] == "USD" for row in positions)
        fx: dict[str, Any] | None = None
        fx_rate_id: str | None = None
        if usd_positions:
            try:
                fx = dict(self.fx_provider.usd_cad())
                fx_rate_id = self.repository.save_fx(fx)
            except Exception as exc:
                fx = self.repository.latest_fx()
                if fx is None:
                    warnings.append(
                        f"USD/CAD conversion unavailable: {type(exc).__name__}. "
                        "USD positions are not included in the CAD total."
                    )
                else:
                    fx_rate_id = str(fx["id"])
                    fx["stale"] = 1
                    warnings.append("Using the last cached USD/CAD rate because refresh failed.")
        usd_cad = _decimal(fx.get("rate")) if fx else None
        if fx and bool(fx.get("stale")):
            warnings.append("The USD/CAD exchange rate is stale.")

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
                        "currency": position["trading_currency"],
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
                    if quote["currency"] != position["trading_currency"]:
                        raise RuntimeError(
                            f"quote currency {quote['currency']} conflicts with "
                            f"{position['trading_currency']}"
                        )
                quote_id = self.repository.save_quote(instrument_id, quote)
                quotes[instrument_id] = (quote_id, quote)
            except Exception as exc:
                quotes[instrument_id] = None
                warnings.append(
                    f"{position['canonical_symbol']}: latest price unavailable ({type(exc).__name__})."
                )

        valued: list[dict[str, Any]] = []
        total_cad = Decimal("0")
        priced = 0
        now = datetime.now(UTC).isoformat()
        for position in positions:
            quote_entry = quotes.get(str(position["instrument_id"]))
            quote_id: str | None = None
            quote: dict[str, Any] | None = None
            data_status = "missing"
            if quote_entry is not None:
                quote_id, quote = quote_entry
                data_status = "stale" if quote["stale"] else str(quote["quote_status"])
            else:
                imported_price = _decimal(position.get("imported_price"))
                if imported_price is not None and imported_price > 0:
                    quote = {
                        "price": _text(imported_price),
                        "currency": position["trading_currency"],
                        "observed_at": now,
                        "fetched_at": now,
                        "source": "Wealthsimple holdings import",
                        "source_url": None,
                        "quote_status": "imported",
                        "delay_minutes": None,
                        "stale": True,
                    }
                    quote_id = self.repository.save_quote(str(position["instrument_id"]), quote)
                    data_status = "imported_stale"
                    warnings.append(
                        f"{position['canonical_symbol']}: using the imported price, "
                        "clearly marked stale, because price refresh failed."
                    )

            quantity = _decimal(position["quantity"]) or Decimal("0")
            price = _decimal(quote.get("price")) if quote else None
            market_trading = quantity * price if price is not None else None
            conversion = (
                Decimal("1")
                if position["trading_currency"] == "CAD"
                else usd_cad
                if position["trading_currency"] == "USD"
                else None
            )
            market_cad = market_trading * conversion if market_trading is not None and conversion else None
            average_cost = _decimal(position.get("average_cost"))
            gain_trading = (
                (price - average_cost) * quantity if price is not None and average_cost is not None else None
            )
            gain_cad = gain_trading * conversion if gain_trading is not None and conversion else None
            if market_cad is not None:
                total_cad += market_cad
                priced += 1
            elif price is not None and conversion is None:
                data_status = "missing_fx"
            valued.append(
                {
                    **position,
                    "price_quote_id": quote_id,
                    "market_value_trading": _text(market_trading),
                    "market_value_cad": _text(market_cad),
                    "unrealized_gain_loss_trading": _text(gain_trading),
                    "unrealized_gain_loss_cad": _text(gain_cad),
                    "portfolio_weight": None,
                    "data_status": data_status,
                }
            )

        if total_cad > 0:
            for row in valued:
                market_cad = _decimal(row["market_value_cad"])
                if market_cad is not None:
                    row["portfolio_weight"] = _text(market_cad / total_cad)
        total_positions = len(positions)
        coverage = Decimal(priced) / Decimal(total_positions) if total_positions else Decimal("0")
        if priced != total_positions:
            warnings.append(
                f"Only {priced} of {total_positions} positions are included in the CAD total; "
                "weights are relative to priced positions only."
            )
        warnings.append(
            "Economic currency exposure is not calculated in Phase 1; trading currency is shown instead."
        )
        return self.repository.save_valuation(
            holding_snapshot_id=snapshot_id,
            total_cad=_text(total_cad) or "0",
            priced_positions=priced,
            total_positions=total_positions,
            coverage_pct=_text(coverage) or "0",
            fx_rate_id=fx_rate_id,
            warnings=list(dict.fromkeys(warnings)),
            positions=valued,
        )

    def latest(self) -> dict[str, Any] | None:
        return self.repository.latest_portfolio()

    def price_capabilities(self) -> dict[str, Any]:
        supported = bool(getattr(self.price_provider, "supports_automatic_refresh", False))
        interval = getattr(self.price_provider, "automatic_refresh_seconds", None)
        safe_interval = max(30, min(60, int(interval))) if supported and interval else None
        return {
            "provider": str(getattr(self.price_provider, "source", type(self.price_provider).__name__)),
            "automatic_refresh_supported": supported,
            "automatic_refresh_seconds": safe_interval,
        }

    def remove_position(self, position_id: str) -> dict[str, str]:
        holding_snapshot_id, symbol = self.repository.create_snapshot_without_position(position_id)
        valuation_snapshot_id = self.refresh(holding_snapshot_id)
        return {
            "holding_snapshot_id": holding_snapshot_id,
            "valuation_snapshot_id": valuation_snapshot_id,
            "removed_symbol": symbol,
        }

    def history(self, limit: int = 180) -> list[dict[str, Any]]:
        return self.repository.portfolio_history(limit)
