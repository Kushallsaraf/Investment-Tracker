"""Transparent portfolio sector allocation with dated ETF holdings evidence."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.repository import PortfolioRepository

SECTOR_OPTIONS: tuple[str, ...] = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
    "Other",
)
DISPLAY_SECTORS = set(SECTOR_OPTIONS) | {"Cash", "Unknown"}
PROFILE_PATH = Path(__file__).resolve().parents[1] / "data" / "etf_sector_profiles.json"
STALE_AFTER_DAYS = 120


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return result if result.is_finite() else None


def _text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


class SectorService:
    def __init__(
        self,
        repository: PortfolioRepository | None = None,
        *,
        profile_path: Path = PROFILE_PATH,
        today: date | None = None,
    ) -> None:
        self.repository = repository or PortfolioRepository()
        self.profile_path = profile_path
        self.today = today

    def _profiles(self) -> dict[str, dict[str, Any]]:
        with self.profile_path.open(encoding="utf-8") as handle:
            profiles: dict[str, dict[str, Any]] = json.load(handle)
        return profiles

    def update_direct_sector(self, instrument_id: str, sector: str | None) -> None:
        if sector is not None and sector not in SECTOR_OPTIONS:
            raise ValueError("Unsupported sector classification")
        self.repository.update_instrument_sector(instrument_id, sector)

    def latest(self) -> dict[str, Any] | None:
        portfolio = self.repository.latest_portfolio()
        if portfolio is None:
            return None

        profiles = self._profiles()
        effective_today = self.today or datetime.now(UTC).date()
        allocation: defaultdict[str, Decimal] = defaultdict(Decimal)
        warnings: list[str] = []
        evidence: dict[str, dict[str, Any]] = {}
        total = _decimal(portfolio["total_value"]) or Decimal("0")
        covered = Decimal("0")
        etf_value = Decimal("0")
        etf_covered = Decimal("0")

        for holding in portfolio["holdings"]:
            value = _decimal(holding.get("market_value"))
            if value is None:
                warnings.append(
                    f"{holding['canonical_symbol']}: no market value, so it is excluded "
                    "from sector allocation."
                )
                continue
            asset_type = holding["asset_type"]
            symbol = holding["canonical_symbol"]

            if asset_type == "CASH":
                allocation["Cash"] += value
                covered += value
                continue

            if asset_type == "STOCK":
                sector = holding.get("manual_sector")
                if sector not in SECTOR_OPTIONS:
                    allocation["Unknown"] += value
                    warnings.append(
                        f"{symbol}: choose a sector in the holdings grid to include this stock "
                        "in known-sector coverage."
                    )
                else:
                    allocation[sector] += value
                    covered += value
                continue

            etf_value += value
            profile = profiles.get(symbol)
            if profile is None:
                allocation["Unknown"] += value
                warnings.append(
                    f"{symbol}: no verified issuer sector profile is available; ETF exposure is Unknown."
                )
                evidence.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "issuer": None,
                        "as_of": None,
                        "verified_on": None,
                        "source_url": None,
                        "method": "No supported issuer profile",
                        "stale": None,
                        "coverage_pct": "0",
                    },
                )
                continue

            sector_weights = {
                sector: _decimal(weight) or Decimal("0")
                for sector, weight in profile["sectors"].items()
                if sector in DISPLAY_SECTORS
            }
            reported_total = sum(sector_weights.values(), Decimal("0"))
            if reported_total <= 0:
                allocation["Unknown"] += value
                warnings.append(f"{symbol}: issuer sector weights are unusable; exposure is Unknown.")
                continue

            # Normalize tiny issuer rounding differences so every ETF contributes exactly its value.
            known_fraction = Decimal("0")
            for sector, weight in sector_weights.items():
                fraction = weight / reported_total
                allocation[sector] += value * fraction
                if sector != "Unknown":
                    known_fraction += fraction
            known_value = value * min(known_fraction, Decimal("1"))
            covered += known_value
            etf_covered += known_value

            as_of = date.fromisoformat(profile["as_of"])
            age_days = (effective_today - as_of).days
            stale = age_days > STALE_AFTER_DAYS
            if stale:
                warnings.append(
                    f"{symbol}: issuer sector evidence is {age_days} days old (as of {profile['as_of']})."
                )
            evidence.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "issuer": profile["issuer"],
                    "as_of": profile["as_of"],
                    "verified_on": profile["verified_on"],
                    "source_url": profile["source_url"],
                    "method": profile["method"],
                    "stale": stale,
                    "coverage_pct": _text(known_fraction),
                },
            )

        categories = [
            {
                "sector": sector,
                "market_value": _text(value),
                "portfolio_weight": _text(value / total) if total else "0",
            }
            for sector, value in sorted(allocation.items(), key=lambda item: item[1], reverse=True)
            if value > 0
        ]
        if evidence:
            warnings.append(
                "ETF weights use issuer-published aggregate sector allocations, normalized for "
                "rounding; holdings can change after the stated as-of date."
            )
        return {
            "valuation_snapshot_id": portfolio["valuation_snapshot_id"],
            "calculated_at": datetime.now(UTC).isoformat(),
            "total_value": _text(total),
            "covered_value": _text(covered),
            "coverage_pct": _text(covered / total) if total else "0",
            "etf_value": _text(etf_value),
            "etf_covered_value": _text(etf_covered),
            "etf_coverage_pct": _text(etf_covered / etf_value) if etf_value else "1",
            "categories": categories,
            "evidence": list(evidence.values()),
            "warnings": list(dict.fromkeys(warnings)),
            "sector_options": list(SECTOR_OPTIONS),
        }
