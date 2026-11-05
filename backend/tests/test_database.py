from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app.database import Database


def test_schema_is_created_once_and_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "fresh.sqlite3"
    Database(path)
    Database(path)
    with sqlite3.connect(path) as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert versions == [1, 2, 3, 4, 5, 6, 7]
    expected = {
        "instruments", "positions", "activities", "ai_reviews",
        "price_bars", "watchlist", "notes", "exit_plans",
    }
    assert expected <= tables
    assert not any("snaptrade" in table or "fx" in table for table in tables)
    assert path.stat().st_mode & 0o777 == 0o600


def test_schema_rejects_unknown_origins_and_activity_types(tmp_path: Path) -> None:
    database = Database(tmp_path / "checks.sqlite3")
    with database.connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO holding_snapshots (id, created_at, source_type, data_origin, position_count) "
            "VALUES ('a', '2026-01-01', 'manual_edit', 'snaptrade', 0)"
        )
    with database.connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO activities (id, activity_type, trade_date, data_origin, created_at) "
            "VALUES ('b', 'DISTRIBUTION', '2026-01-01', 'manual', '2026-01-01')"
        )
