"""Cached SEC EDGAR payloads and editable peer lists."""

from __future__ import annotations

import json
from typing import Any

from app.database import Database
from app.repository import utc_now


class SecRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def cached(self, key: str) -> tuple[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT fetched_at, payload_json FROM sec_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        return (str(row["fetched_at"]), json.loads(row["payload_json"])) if row else None

    def store(self, key: str, payload: Any, fetched_at: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sec_cache (cache_key, fetched_at, payload_json) VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    fetched_at = excluded.fetched_at, payload_json = excluded.payload_json
                """,
                (key, fetched_at, json.dumps(payload, separators=(",", ":"))),
            )

    def peer_list(self, symbol: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM peer_lists WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["peers"] = json.loads(result.pop("peers_json"))
        return result

    def save_peer_list(
        self,
        symbol: str,
        peers: list[str],
        *,
        source: str,
        sic: str | None = None,
        sic_description: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO peer_lists (symbol, peers_json, source, sic, sic_description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    peers_json = excluded.peers_json, source = excluded.source,
                    sic = COALESCE(excluded.sic, peer_lists.sic),
                    sic_description = COALESCE(excluded.sic_description, peer_lists.sic_description),
                    updated_at = excluded.updated_at
                """,
                (symbol, json.dumps(peers), source, sic, sic_description, utc_now()),
            )

    def delete_peer_list(self, symbol: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM peer_lists WHERE symbol = ?", (symbol,))
