from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import MIGRATIONS, Database


def test_version_one_database_migrates_without_changing_historical_positions(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.executescript(MIGRATIONS[0][1])
        connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")
        connection.execute(
            """
            INSERT INTO instruments
                (id, canonical_symbol, security_name, asset_type, exchange,
                 trading_currency, created_at, updated_at)
            VALUES ('existing', 'XIC.TO', 'Synthetic ETF', 'ETF', 'TSX',
                    'CAD', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO accounts
                (id, source_fingerprint, alias, account_type, created_at)
            VALUES ('account', 'synthetic-fingerprint', 'TFSA-TEST', 'TFSA',
                    '2026-01-01T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO holding_snapshots
                (id, imported_at, source_type, source_file_hash, source_as_of, position_count)
            VALUES ('snapshot', '2026-01-01T00:00:00+00:00', 'synthetic',
                    'synthetic-hash', '2026-01-01', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO positions
                (id, snapshot_id, account_id, instrument_id, source_row_number,
                 quantity, average_cost, imported_price, imported_market_value)
            VALUES ('position', 'snapshot', 'account', 'existing', 2, '1', '30', '40', '40')
            """
        )

    database = Database(path)
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO instruments
                (id, canonical_symbol, security_name, asset_type, exchange,
                 trading_currency, created_at, updated_at)
            VALUES ('cash', 'CASH-CAD', 'Canadian Dollar', 'CASH', 'CASH',
                    'CAD', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:00+00:00')
            """
        )

    with database.connect() as connection:
        symbols = {
            row["canonical_symbol"] for row in connection.execute("SELECT canonical_symbol FROM instruments")
        }
        versions = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
        snaptrade_state = connection.execute(
            "SELECT connection_status FROM snaptrade_sync_state WHERE id = 1"
        ).fetchone()["connection_status"]
        foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
        joined_symbol = connection.execute(
            """
            SELECT i.canonical_symbol
            FROM positions p
            JOIN instruments i ON i.id = p.instrument_id
            WHERE p.id = 'position'
            """
        ).fetchone()["canonical_symbol"]

    assert symbols == {"XIC.TO", "CASH-CAD"}
    assert versions == {1, 2, 3, 4}
    assert snaptrade_state == "not_checked"
    assert foreign_key_errors == []
    assert joined_symbol == "XIC.TO"
