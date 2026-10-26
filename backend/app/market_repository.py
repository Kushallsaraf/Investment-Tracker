"""Persistence for cached daily price history and the research watchlist."""

from __future__ import annotations

from typing import Any

from app.database import Database
from app.repository import utc_now


class MarketRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def symbol(self, symbol: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM market_symbols WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None

    def save_history(self, meta: dict[str, Any], bars: list[dict[str, Any]], fetched_at: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO market_symbols
                    (symbol, security_name, asset_type, exchange, history_fetched_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    security_name = excluded.security_name,
                    asset_type = excluded.asset_type,
                    exchange = excluded.exchange,
                    history_fetched_at = excluded.history_fetched_at,
                    updated_at = excluded.updated_at
                """,
                (
                    meta["symbol"],
                    meta["security_name"],
                    meta["asset_type"],
                    meta["exchange"],
                    fetched_at,
                    utc_now(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO price_bars
                    (symbol, bar_date, open, high, low, close, adj_close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, bar_date) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low,
                    close = excluded.close, adj_close = excluded.adj_close,
                    volume = excluded.volume
                """,
                [
                    (
                        meta["symbol"],
                        bar["date"],
                        bar["open"],
                        bar["high"],
                        bar["low"],
                        bar["close"],
                        bar["adj_close"],
                        bar["volume"],
                    )
                    for bar in bars
                ],
            )

    def bars(self, symbol: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT bar_date AS date, open, high, low, close, adj_close, volume
                FROM price_bars WHERE symbol = ? ORDER BY bar_date
                """,
                (symbol,),
            ).fetchall()
        return [dict(row) for row in rows]

    def watchlist(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT w.symbol, w.position, w.added_at, s.security_name, s.asset_type, s.exchange
                FROM watchlist w JOIN market_symbols s ON s.symbol = w.symbol
                ORDER BY w.position, w.added_at
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_to_watchlist(self, symbol: str) -> None:
        with self.database.transaction() as connection:
            position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM watchlist"
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO watchlist (symbol, position, added_at) VALUES (?, ?, ?)",
                (symbol, position, utc_now()),
            )

    def remove_from_watchlist(self, symbol: str) -> None:
        with self.database.transaction() as connection:
            removed = connection.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,)).rowcount
        if not removed:
            raise KeyError(f"{symbol} is not on the watchlist")
