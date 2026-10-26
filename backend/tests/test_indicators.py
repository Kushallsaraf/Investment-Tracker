from __future__ import annotations

import math

import pytest
from app.services import indicators


def test_simple_and_exponential_averages_warm_up_explicitly() -> None:
    assert indicators.sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]
    assert indicators.ema([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]
    assert indicators.ema([None, 1, 2, 3, 4], 3) == [None, None, None, 2, 3]


def test_bollinger_uses_population_deviation() -> None:
    upper, middle, lower = indicators.bollinger([1, 2, 3], period=3, width=2)
    assert middle == [None, None, 2]
    assert upper[2] == pytest.approx(2 + 2 * math.sqrt(2 / 3))
    assert lower[2] == pytest.approx(2 - 2 * math.sqrt(2 / 3))


def test_rsi_uses_wilder_smoothing() -> None:
    assert indicators.rsi([1, 2, 1, 2, 3], period=2) == [None, None, 50.0, 75.0, 87.5]
    assert indicators.rsi(list(range(1, 30)))[-1] == 100.0
    assert indicators.rsi(list(range(30, 1, -1)))[-1] == pytest.approx(0.0)


def test_atr_uses_true_range_including_gaps() -> None:
    result = indicators.atr([10, 11, 12], [9, 10, 10], [9.5, 10.5, 11], period=2)
    assert result == [None, None, 1.75]


def test_macd_line_and_signal_warm_up_in_order() -> None:
    values = [100 + math.sin(index / 5) * 10 for index in range(60)]
    line, signal, histogram = indicators.macd(values)
    assert line.index(next(value for value in line if value is not None)) == 25
    assert signal.index(next(value for value in signal if value is not None)) == 33
    assert histogram[40] == pytest.approx(line[40] - signal[40])
