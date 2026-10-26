"""Deterministic technical indicators over daily series.

Every function returns a list aligned with its input; positions without enough
history are None rather than a partially warmed-up value.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Series = list[float | None]


def sma(values: Sequence[float], period: int) -> Series:
    result: Series = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            result[index] = running / period
    return result


def ema(values: Sequence[float | None], period: int) -> Series:
    """Exponential average seeded with the simple average of the first full window."""
    result: Series = [None] * len(values)
    alpha = 2 / (period + 1)
    window: list[float] = []
    previous: float | None = None
    for index, value in enumerate(values):
        if value is None:
            continue
        if previous is None:
            window.append(value)
            if len(window) == period:
                previous = sum(window) / period
                result[index] = previous
            continue
        previous = value * alpha + previous * (1 - alpha)
        result[index] = previous
    return result


def bollinger(values: Sequence[float], period: int = 20, width: float = 2.0) -> tuple[Series, Series, Series]:
    middle = sma(values, period)
    upper: Series = [None] * len(values)
    lower: Series = [None] * len(values)
    for index, mean in enumerate(middle):
        if mean is None:
            continue
        window = values[index - period + 1 : index + 1]
        deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
        upper[index] = mean + width * deviation
        lower[index] = mean - width * deviation
    return upper, middle, lower


def _wilder(values: Sequence[float], period: int, start: int) -> Series:
    """Wilder smoothing of values[start:], seeded with a simple average of the first window."""
    result: Series = [None] * len(values)
    if len(values) - start < period:
        return result
    average = sum(values[start : start + period]) / period
    result[start + period - 1] = average
    for index in range(start + period, len(values)):
        average = (average * (period - 1) + values[index]) / period
        result[index] = average
    return result


def rsi(values: Sequence[float], period: int = 14) -> Series:
    changes = [current - previous for previous, current in zip(values, values[1:], strict=False)]
    gains = [0.0] + [max(change, 0.0) for change in changes]
    losses = [0.0] + [max(-change, 0.0) for change in changes]
    average_gain = _wilder(gains, period, 1)
    average_loss = _wilder(losses, period, 1)
    result: Series = [None] * len(values)
    for index, (gain, loss) in enumerate(zip(average_gain, average_loss, strict=True)):
        if gain is None or loss is None:
            continue
        result[index] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return result


def macd(
    values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Series, Series, Series]:
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    line: Series = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_line, slow_line, strict=True)
    ]
    signal_line = ema(line, signal)
    histogram: Series = [
        m - s if m is not None and s is not None else None
        for m, s in zip(line, signal_line, strict=True)
    ]
    return line, signal_line, histogram


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> Series:
    ranges = [highs[0] - lows[0]] + [
        max(high - low, abs(high - previous_close), abs(low - previous_close))
        for high, low, previous_close in zip(highs[1:], lows[1:], closes, strict=False)
    ]
    return _wilder(ranges, period, 1)
