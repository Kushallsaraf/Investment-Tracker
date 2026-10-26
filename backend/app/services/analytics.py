"""Deterministic portfolio analytics with explicit missing-data states."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import correlation, covariance, stdev, variance
from typing import Any

from app.repository import PortfolioRepository
from app.services.sectors import SectorService

CANADIAN_BENCHMARK = "S&P/TSX Composite Total Return Index"


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def _returns(values: list[float]) -> list[float]:
    if len(values) < 2 or any(value <= 0 or not math.isfinite(value) for value in values):
        raise ValueError("At least two positive finite observations are required")
    return [(current / previous) - 1 for previous, current in zip(values, values[1:], strict=False)]


def require_adjusted_total_return(observations: Iterable[dict[str, Any]]) -> list[float]:
    rows = list(observations)
    if any(
        row.get("series_type") != "ADJUSTED_TOTAL_RETURN"
        or not bool(row.get("distributions_included"))
        for row in rows
    ):
        raise ValueError("Raw closes cannot be used where adjusted total return is required")
    values = [float(row["value"]) for row in rows]
    if len(values) < 2:
        raise ValueError("Insufficient adjusted total-return observations")
    return values


def calculate_historical_risk(
    portfolio_observations: Iterable[dict[str, Any]],
    benchmark_observations: Iterable[dict[str, Any]],
    *,
    annualization: int = 252,
) -> dict[str, float]:
    portfolio_values = require_adjusted_total_return(portfolio_observations)
    benchmark_values = require_adjusted_total_return(benchmark_observations)
    if len(portfolio_values) != len(benchmark_values) or len(portfolio_values) < 3:
        raise ValueError("Aligned portfolio and benchmark history is insufficient")
    portfolio_returns = _returns(portfolio_values)
    benchmark_returns = _returns(benchmark_values)
    benchmark_variance = variance(benchmark_returns)
    if benchmark_variance == 0:
        raise ValueError("Benchmark variance is zero; beta is unavailable")
    peak = portfolio_values[0]
    maximum_drawdown = 0.0
    for value in portfolio_values:
        peak = max(peak, value)
        maximum_drawdown = min(maximum_drawdown, (value / peak) - 1)
    return {
        "annualized_volatility": stdev(portfolio_returns) * math.sqrt(annualization),
        "maximum_drawdown": maximum_drawdown,
        "beta": covariance(portfolio_returns, benchmark_returns) / benchmark_variance,
        "correlation": correlation(portfolio_returns, benchmark_returns),
    }


def time_weighted_return(values: list[float], external_cash_flows: list[float]) -> float:
    """Calculate linked returns; only deposits/withdrawals belong in external_cash_flows."""
    if len(values) < 2 or len(external_cash_flows) != len(values) - 1:
        raise ValueError("Values and external cash-flow periods do not align")
    linked = 1.0
    for previous, current, external_flow in zip(
        values, values[1:], external_cash_flows, strict=False
    ):
        if previous <= 0:
            raise ValueError("Portfolio values must be positive")
        linked *= 1 + ((current - external_flow) / previous - 1)
    return linked - 1


def etf_overlap(
    first: dict[str, float], second: dict[str, float], *, first_coverage: float, second_coverage: float
) -> dict[str, Any]:
    duplicated = {
        key: min(first[key], second[key]) for key in first.keys() & second.keys()
    }
    largest = sorted(duplicated.items(), key=lambda item: item[1], reverse=True)
    return {
        "overlap_by_weight": sum(duplicated.values()),
        "largest_duplicated_holdings": [key for key, _weight in largest[:5]],
        "coverage": min(first_coverage, second_coverage),
    }


class AnalyticsService:
    def __init__(
        self,
        repository: PortfolioRepository,
        sectors: SectorService,
    ) -> None:
        self.repository = repository
        self.sectors = sectors

    def _concentration(self, portfolio: dict[str, Any] | None) -> dict[str, Any]:
        if portfolio is None:
            return {
                "status": "missing",
                "reason": "No accepted portfolio snapshot exists.",
                "as_of": None,
            }
        holdings = portfolio["holdings"]
        valued = [
            row for row in holdings if _decimal(row.get("portfolio_weight")) is not None
        ]
        weights = sorted(
            (_decimal(row["portfolio_weight"]) or Decimal("0") for row in valued),
            reverse=True,
        )
        by_type: dict[str, Decimal] = {"STOCK": Decimal("0"), "ETF": Decimal("0"), "CASH": Decimal("0")}
        for row in valued:
            by_type[row["asset_type"]] += _decimal(row["portfolio_weight"]) or Decimal("0")
        return {
            "status": "available",
            "largest_holding_weight": format(weights[0], "f") if weights else "0",
            "top_five_weight": format(sum(weights[:5], Decimal("0")), "f"),
            "stock_weight": format(by_type["STOCK"], "f"),
            "etf_weight": format(by_type["ETF"], "f"),
            "cash_weight": format(by_type["CASH"], "f"),
            "missing_data_pct": format(
                Decimal(portfolio["total_positions"] - portfolio["priced_positions"])
                / Decimal(portfolio["total_positions"])
                if portfolio["total_positions"]
                else Decimal("0"),
                "f",
            ),
            "missing_data_basis": "share of positions without a CAD valuation",
            "as_of": portfolio["created_at"],
            "source": "Latest immutable local valuation snapshot",
        }

    def _economic_exposure(self, portfolio: dict[str, Any] | None) -> dict[str, Any]:
        if portfolio is None:
            return {"status": "missing", "categories": [], "coverage_pct": "0"}
        total = _decimal(portfolio["total_cad"]) or Decimal("0")
        cash = sum(
            (
                _decimal(row.get("market_value_cad")) or Decimal("0")
                for row in portfolio["holdings"]
                if row["asset_type"] == "CASH"
            ),
            Decimal("0"),
        )
        unknown = max(Decimal("0"), total - cash)
        categories = []
        if cash:
            categories.append(
                {
                    "name": "Cash",
                    "weight": format(cash / total, "f") if total else "0",
                    "market_value_cad": format(cash, "f"),
                }
            )
        if unknown:
            categories.append(
                {
                    "name": "Unknown",
                    "weight": format(unknown / total, "f") if total else "0",
                    "market_value_cad": format(unknown, "f"),
                }
            )
        return {
            "status": "partial" if total else "missing",
            "categories": categories,
            "coverage_pct": format(cash / total, "f") if total else "0",
            "etf_lookthrough_available": False,
            "as_of": portfolio["created_at"],
            "source": "Local cash classification only",
            "warning": (
                "Economic exposure is unavailable for securities and ETFs. Trading currency "
                "has not been substituted. Only cash is classified."
            ),
        }

    def _trading_currency(self, portfolio: dict[str, Any] | None) -> list[dict[str, str]]:
        if portfolio is None:
            return []
        total = _decimal(portfolio["total_cad"]) or Decimal("0")
        buckets: dict[str, Decimal] = {}
        for row in portfolio["holdings"]:
            value = _decimal(row.get("market_value_cad"))
            if value is not None:
                currency = str(row["trading_currency"])
                buckets[currency] = buckets.get(currency, Decimal("0")) + value
        return [
            {
                "currency": currency,
                "weight": format(value / total, "f") if total else "0",
            }
            for currency, value in sorted(buckets.items())
        ]

    def overview(self) -> dict[str, Any]:
        portfolio = self.repository.latest_portfolio()
        sector_analysis = self.sectors.latest()
        generated_at = datetime.now(UTC).isoformat()
        adjusted_missing = (
            "Verified adjusted total-return series and complete external cash-flow history "
            "are not available. Current holdings are not backfilled and raw prices are not substituted."
        )
        risk_missing = (
            "Aligned adjusted total-return observations for the portfolio and benchmark are not available."
        )
        return {
            "generated_at": generated_at,
            "concentration": self._concentration(portfolio),
            "economic_exposure": self._economic_exposure(portfolio),
            "trading_currency": self._trading_currency(portfolio),
            "performance": {
                "status": "insufficient_transaction_history",
                "label": "INSUFFICIENT TRANSACTION HISTORY",
                "reason": adjusted_missing,
                "benchmark": CANADIAN_BENCHMARK,
                "portfolio_return": None,
                "benchmark_return": None,
                "difference": None,
                "periods": [],
                "currency": "CAD",
                "distributions_included": None,
                "source": None,
                "as_of": None,
                "coverage_pct": "0",
            },
            "risk": {
                "status": "missing",
                "label": "NOT AVAILABLE",
                "reason": risk_missing,
                "benchmark": CANADIAN_BENCHMARK,
                "measurement_period": None,
                "observation_frequency": None,
                "annualized_volatility": None,
                "maximum_drawdown": None,
                "beta": None,
                "correlation": None,
                "source": None,
                "as_of": None,
                "coverage_pct": "0",
                "disclaimer": "Historical risk · not a forecast",
            },
            "currency_exposure": {
                "status": "missing",
                "label": "NOT AVAILABLE",
                "reason": (
                    "Underlying economic currency exposure is not available from verified issuer "
                    "or company evidence. Listing currency is shown separately and is not substituted."
                ),
                "categories": [{"currency": "Unknown", "weight": "1"}] if portfolio else [],
                "trading_currency": self._trading_currency(portfolio),
                "coverage_pct": "0",
                "source": None,
                "as_of": None,
            },
            "etf_lookthrough": {
                "status": "partial" if (sector_analysis or {}).get("evidence") else "missing",
                "overlap": [],
                "weighted_mer": None,
                "sector_allocation": (sector_analysis or {}).get("categories", []),
                "country_allocation": [],
                "evidence": (sector_analysis or {}).get("evidence", []),
                "coverage_pct": (sector_analysis or {}).get("etf_coverage_pct", "0"),
                "warning": (
                    "Only the explicitly listed issuer sector profiles are supported. Verified "
                    "constituent holdings and MER evidence are not yet stored, so overlap, country "
                    "allocation, and weighted MER are not estimated."
                ),
            },
        }
