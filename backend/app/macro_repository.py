"""Cached macro payloads (FRED series, release calendars, FOMC meetings)."""

from __future__ import annotations

import json
from typing import Any

from app.database import Database


class MacroRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, key: str) -> tuple[Any, str] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT fetched_at, payload_json FROM macro_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        return (json.loads(row["payload_json"]), row["fetched_at"]) if row else None

    def put(self, key: str, payload: Any, fetched_at: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO macro_cache (cache_key, fetched_at, payload_json) VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    fetched_at = excluded.fetched_at, payload_json = excluded.payload_json
                """,
                (key, fetched_at, json.dumps(payload)),
            )
