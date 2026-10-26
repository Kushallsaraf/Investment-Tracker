"""Synthetic demonstration portfolio. Quantities, costs, and activities are illustrative only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

DEMO_ACCOUNT = "Demo brokerage"

DEMO_POSITIONS: tuple[dict[str, Any], ...] = (
    {"canonical_symbol": "AAPL", "security_name": "Apple Inc.", "asset_type": "STOCK",
     "exchange": "NasdaqGS", "quantity": "40", "average_cost": "152.30",
     "manual_sector": "Information Technology"},
    {"canonical_symbol": "MSFT", "security_name": "Microsoft Corporation", "asset_type": "STOCK",
     "exchange": "NasdaqGS", "quantity": "18", "average_cost": "301.75",
     "manual_sector": "Information Technology"},
    {"canonical_symbol": "NVDA", "security_name": "NVIDIA Corporation", "asset_type": "STOCK",
     "exchange": "NasdaqGS", "quantity": "60", "average_cost": "48.10",
     "manual_sector": "Information Technology"},
    {"canonical_symbol": "JPM", "security_name": "JPMorgan Chase & Co.", "asset_type": "STOCK",
     "exchange": "NYSE", "quantity": "25", "average_cost": "141.20", "manual_sector": "Financials"},
    {"canonical_symbol": "JNJ", "security_name": "Johnson & Johnson", "asset_type": "STOCK",
     "exchange": "NYSE", "quantity": "20", "average_cost": "158.40", "manual_sector": "Health Care"},
    {"canonical_symbol": "XOM", "security_name": "Exxon Mobil Corporation", "asset_type": "STOCK",
     "exchange": "NYSE", "quantity": "30", "average_cost": "98.65", "manual_sector": "Energy"},
    {"canonical_symbol": "VOO", "security_name": "Vanguard S&P 500 ETF", "asset_type": "ETF",
     "exchange": "NYSEArca", "quantity": "22", "average_cost": "384.90"},
    {"canonical_symbol": "QQQ", "security_name": "Invesco QQQ Trust, Series 1", "asset_type": "ETF",
     "exchange": "NasdaqGM", "quantity": "10", "average_cost": "352.15"},
    {"canonical_symbol": "USD", "security_name": "US dollar cash", "asset_type": "CASH",
     "exchange": "CASH", "quantity": "2450.00", "average_cost": "1"},
)

# (days before today, type, symbol, quantity, price, cash amount)
_DEMO_ACTIVITY: tuple[tuple[int, str, str | None, str | None, str | None, str], ...] = (
    (720, "DEPOSIT", None, None, None, "40000.00"),
    (715, "BUY", "VOO", "22", "384.90", "-8467.80"),
    (712, "BUY", "AAPL", "40", "152.30", "-6092.00"),
    (700, "BUY", "MSFT", "18", "301.75", "-5431.50"),
    (690, "BUY", "JPM", "25", "141.20", "-3530.00"),
    (680, "BUY", "JNJ", "20", "158.40", "-3168.00"),
    (600, "BUY", "NVDA", "60", "48.10", "-2886.00"),
    (540, "BUY", "XOM", "30", "98.65", "-2959.50"),
    (420, "BUY", "QQQ", "10", "352.15", "-3521.50"),
    (330, "DIVIDEND", "VOO", None, None, "35.42"),
    (320, "DIVIDEND", "JPM", None, None, "28.75"),
    (300, "DIVIDEND", "XOM", None, None, "28.50"),
    (290, "DIVIDEND", "JNJ", None, None, "24.80"),
    (240, "DIVIDEND", "VOO", None, None, "36.10"),
    (230, "DIVIDEND", "JPM", None, None, "31.25"),
    (210, "DIVIDEND", "XOM", None, None, "29.70"),
    (200, "DIVIDEND", "JNJ", None, None, "24.80"),
    (180, "DIVIDEND", "AAPL", None, None, "10.00"),
    (170, "DIVIDEND", "MSFT", None, None, "14.94"),
    (150, "DIVIDEND", "VOO", None, None, "37.05"),
    (140, "DIVIDEND", "JPM", None, None, "31.25"),
    (120, "DIVIDEND", "XOM", None, None, "29.70"),
    (110, "DIVIDEND", "JNJ", None, None, "26.00"),
    (95, "DIVIDEND", "AAPL", None, None, "10.40"),
    (85, "DIVIDEND", "MSFT", None, None, "14.94"),
    (60, "DIVIDEND", "VOO", None, None, "37.80"),
    (45, "INTEREST", None, None, None, "6.12"),
    (30, "FEE", None, None, None, "-4.95"),
)


def demo_activities(today: date) -> list[dict[str, Any]]:
    return [
        {
            "activity_type": activity_type,
            "symbol": symbol,
            "trade_date": (today - timedelta(days=days)).isoformat(),
            "quantity": quantity,
            "price": price,
            "fee": None,
            "cash_amount": cash_amount,
            "note": "Synthetic demo activity",
        }
        for days, activity_type, symbol, quantity, price, cash_amount in _DEMO_ACTIVITY
    ]


def demo_positions() -> list[dict[str, Any]]:
    return [{**row, "account_name": DEMO_ACCOUNT} for row in DEMO_POSITIONS]
