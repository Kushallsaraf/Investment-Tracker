from __future__ import annotations

import math

import pytest
from app.services.analytics import (
    calculate_historical_risk,
    etf_overlap,
    require_adjusted_total_return,
    time_weighted_return,
)


def adjusted(values: list[float]) -> list[dict[str, object]]:
    return [
        {
            "value": value,
            "series_type": "ADJUSTED_TOTAL_RETURN",
            "distributions_included": True,
        }
        for value in values
    ]


def test_adjusted_total_return_is_required_and_raw_closes_are_rejected() -> None:
    assert require_adjusted_total_return(adjusted([100, 102])) == [100.0, 102.0]
    with pytest.raises(ValueError, match="Raw closes"):
        require_adjusted_total_return(
            [{"value": 100, "series_type": "RAW_CLOSE", "distributions_included": False}]
        )


def test_historical_risk_metrics_are_deterministic() -> None:
    result = calculate_historical_risk(
        adjusted([100, 110, 88, 105]),
        adjusted([100, 105, 94.5, 103.95]),
        annualization=12,
    )
    assert result["maximum_drawdown"] == pytest.approx(-0.2)
    assert result["annualized_volatility"] > 0
    assert math.isfinite(result["beta"])
    assert -1 <= result["correlation"] <= 1


def test_time_weighted_return_treats_only_external_cash_flows_as_flows() -> None:
    # 100 grows 10%, then a 50 deposit brings value to 160; the next period also grows 10%.
    assert time_weighted_return([100, 160, 176], [50, 0]) == pytest.approx(0.21)


def test_etf_overlap_includes_coverage_and_largest_duplicates() -> None:
    result = etf_overlap(
        {"RY": 0.10, "TD": 0.08, "CNR": 0.04},
        {"RY": 0.06, "TD": 0.09, "SHOP": 0.05},
        first_coverage=0.98,
        second_coverage=0.91,
    )
    assert result["overlap_by_weight"] == pytest.approx(0.14)
    assert result["largest_duplicated_holdings"] == ["TD", "RY"]
    assert result["coverage"] == 0.91
