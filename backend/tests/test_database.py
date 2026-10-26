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
        preserved_position = dict(
            connection.execute(
                "SELECT snapshot_id, source_row_number, quantity, average_cost, "
                "imported_price, imported_market_value FROM positions WHERE id = 'position'"
            ).fetchone()
        )
        preserved_snapshot = dict(
            connection.execute(
                "SELECT imported_at, source_type, source_file_hash, source_as_of, "
                "position_count, data_origin FROM holding_snapshots WHERE id = 'snapshot'"
            ).fetchone()
        )
        new_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert symbols == {"XIC.TO", "CASH-CAD"}
    assert versions == {version for version, _sql in MIGRATIONS}
    assert snaptrade_state == "not_checked"
    assert foreign_key_errors == []
    assert joined_symbol == "XIC.TO"
    assert preserved_position == {
        "snapshot_id": "snapshot",
        "source_row_number": 2,
        "quantity": "1",
        "average_cost": "30",
        "imported_price": "40",
        "imported_market_value": "40",
    }
    assert preserved_snapshot == {
        "imported_at": "2026-01-01T00:00:00+00:00",
        "source_type": "synthetic",
        "source_file_hash": "synthetic-hash",
        "source_as_of": "2026-01-01",
        "position_count": 1,
        "data_origin": "legacy",
    }
    assert {
        "brokerage_activities",
        "decision_history",
        "review_triggers",
        "claude_prompts",
        "ai_reviews",
        "historical_price_observations",
        "etf_evidence_profiles",
    } <= new_tables


def test_activity_revision_schema_repair_preserves_snapshots_and_pending_preview(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schema-drift.sqlite3"
    database = Database(path)
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO holding_snapshots
                (id, imported_at, source_type, source_file_hash, source_as_of,
                 position_count, data_origin)
            VALUES ('snapshot', '2026-01-01T00:00:00+00:00', 'snaptrade_read_sync',
                    'synthetic-hash', '2026-01-01', 0, 'snaptrade')
            """
        )
        connection.execute(
            """
            INSERT INTO snaptrade_sync_previews
                (id, created_at, expires_at, rows_json, changes_json, issues_json,
                 activities_json, activity_summary_json)
            VALUES ('preview', '2026-01-02T00:00:00+00:00',
                    '2026-01-03T00:00:00+00:00', '[]', '[]', '[]', '[]', '{}')
            """
        )
        connection.execute("DROP TABLE brokerage_activity_revisions")
        connection.execute("DELETE FROM schema_migrations WHERE version = 7")

    repaired = Database(path)
    with repaired.connect() as connection:
        versions = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'brokerage_activity_revisions'"
        ).fetchone()
        index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_brokerage_activity_revisions_key'"
        ).fetchone()
        snapshots = [
            dict(row)
            for row in connection.execute(
                "SELECT id, imported_at, source_type, source_file_hash, source_as_of, "
                "position_count, data_origin FROM holding_snapshots"
            )
        ]
        previews = [
            dict(row)
            for row in connection.execute(
                "SELECT id, rows_json, changes_json, issues_json, activities_json, "
                "activity_summary_json FROM snaptrade_sync_previews"
            )
        ]
        foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))

    assert versions == {version for version, _sql in MIGRATIONS}
    assert table["name"] == "brokerage_activity_revisions"
    assert index["name"] == "idx_brokerage_activity_revisions_key"
    assert snapshots == [
        {
            "id": "snapshot",
            "imported_at": "2026-01-01T00:00:00+00:00",
            "source_type": "snaptrade_read_sync",
            "source_file_hash": "synthetic-hash",
            "source_as_of": "2026-01-01",
            "position_count": 0,
            "data_origin": "snaptrade",
        }
    ]
    assert previews == [
        {
            "id": "preview",
            "rows_json": "[]",
            "changes_json": "[]",
            "issues_json": "[]",
            "activities_json": "[]",
            "activity_summary_json": "{}",
        }
    ]
    assert foreign_key_errors == []

    with repaired.transaction() as connection:
        connection.execute(
            """
            INSERT INTO brokerage_activity_revisions
                (id, activity_key, record_hash, normalized_json, observed_at,
                 holding_snapshot_id)
            VALUES ('revision', 'synthetic-key', 'synthetic-hash', '{}',
                    '2026-01-02T00:00:00+00:00', 'snapshot')
            """
        )
    Database(path)
    with repaired.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM brokerage_activity_revisions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 7"
        ).fetchone()[0] == 1
