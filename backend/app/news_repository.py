"""Stored headlines, 8-K filings, and their sentiment scores."""

from __future__ import annotations

import json
from typing import Any

from app.database import Database
from app.repository import utc_now


class NewsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def last_fetch(self, symbol: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM news_fetches WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            return None
        return {"fetched_at": row["fetched_at"], "failures": json.loads(row["failures_json"])}

    def save_items(
        self, symbol: str, items: list[dict[str, Any]], failures: dict[str, str], fetched_at: str
    ) -> None:
        """Add items not seen before (existing ones keep their scores) and record the fetch."""
        now = fetched_at
        with self.database.transaction() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO news_items
                    (id, symbol, kind, title, summary, url, publisher, published_at, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["id"],
                        symbol,
                        item["kind"],
                        item["title"],
                        item.get("summary"),
                        item["url"],
                        item["publisher"],
                        item["published_at"],
                        now,
                    )
                    for item in items
                ],
            )
            connection.execute(
                """
                INSERT INTO news_fetches (symbol, fetched_at, failures_json) VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    fetched_at = excluded.fetched_at, failures_json = excluded.failures_json
                """,
                (symbol, now, json.dumps(failures)),
            )

    def items(self, symbol: str, since: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM news_items WHERE symbol = ? AND published_at >= ? ORDER BY published_at DESC",
                (symbol, since),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_scores(self, scores: dict[str, dict[str, float]], model: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.executemany(
                """
                UPDATE news_items
                SET positive = ?, neutral = ?, negative = ?, sentiment_model = ?, scored_at = ?
                WHERE id = ?
                """,
                [
                    (row["positive"], row["neutral"], row["negative"], model, now, item_id)
                    for item_id, row in scores.items()
                ],
            )
