"""SQLite connection management and explicit schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            source_fingerprint TEXT NOT NULL UNIQUE,
            alias TEXT NOT NULL UNIQUE,
            account_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS instruments (
            id TEXT PRIMARY KEY,
            canonical_symbol TEXT NOT NULL UNIQUE,
            security_name TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'ETF')),
            exchange TEXT NOT NULL,
            trading_currency TEXT NOT NULL CHECK (trading_currency IN ('CAD', 'USD')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS holding_snapshots (
            id TEXT PRIMARY KEY,
            imported_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_file_hash TEXT NOT NULL,
            source_as_of TEXT,
            position_count INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_holding_snapshots_imported
            ON holding_snapshots(imported_at DESC);
        CREATE INDEX IF NOT EXISTS idx_holding_snapshots_hash
            ON holding_snapshots(source_file_hash);

        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES holding_snapshots(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            instrument_id TEXT NOT NULL REFERENCES instruments(id),
            source_row_number INTEGER NOT NULL,
            quantity TEXT NOT NULL,
            average_cost TEXT,
            imported_price TEXT,
            imported_market_value TEXT,
            UNIQUE(snapshot_id, account_id, instrument_id)
        );

        CREATE TABLE IF NOT EXISTS price_quotes (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL REFERENCES instruments(id),
            price TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency IN ('CAD', 'USD')),
            observed_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            quote_status TEXT NOT NULL,
            delay_minutes INTEGER,
            stale INTEGER NOT NULL CHECK (stale IN (0, 1))
        );
        CREATE INDEX IF NOT EXISTS idx_price_quotes_instrument_time
            ON price_quotes(instrument_id, fetched_at DESC);

        CREATE TABLE IF NOT EXISTS fx_rates (
            id TEXT PRIMARY KEY,
            base_currency TEXT NOT NULL,
            quote_currency TEXT NOT NULL,
            rate TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            stale INTEGER NOT NULL CHECK (stale IN (0, 1))
        );
        CREATE INDEX IF NOT EXISTS idx_fx_rates_pair_time
            ON fx_rates(base_currency, quote_currency, fetched_at DESC);

        CREATE TABLE IF NOT EXISTS valuation_snapshots (
            id TEXT PRIMARY KEY,
            holding_snapshot_id TEXT NOT NULL REFERENCES holding_snapshots(id),
            created_at TEXT NOT NULL,
            total_cad TEXT NOT NULL,
            priced_positions INTEGER NOT NULL,
            total_positions INTEGER NOT NULL,
            position_coverage_pct TEXT NOT NULL,
            fx_rate_id TEXT REFERENCES fx_rates(id),
            warnings_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_valuation_snapshots_created
            ON valuation_snapshots(created_at DESC);

        CREATE TABLE IF NOT EXISTS position_valuations (
            id TEXT PRIMARY KEY,
            valuation_snapshot_id TEXT NOT NULL REFERENCES valuation_snapshots(id) ON DELETE CASCADE,
            position_id TEXT NOT NULL REFERENCES positions(id),
            price_quote_id TEXT REFERENCES price_quotes(id),
            market_value_trading TEXT,
            market_value_cad TEXT,
            unrealized_gain_loss_trading TEXT,
            unrealized_gain_loss_cad TEXT,
            portfolio_weight TEXT,
            data_status TEXT NOT NULL,
            UNIQUE(valuation_snapshot_id, position_id)
        );

        CREATE TABLE IF NOT EXISTS import_drafts (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            source_file_hash TEXT NOT NULL,
            rows_json TEXT NOT NULL,
            issues_json TEXT NOT NULL,
            ignored_columns_json TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        PRAGMA foreign_keys = OFF;
        BEGIN IMMEDIATE;

        CREATE TABLE instruments_v2 (
            id TEXT PRIMARY KEY,
            canonical_symbol TEXT NOT NULL UNIQUE,
            security_name TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'ETF', 'CASH')),
            exchange TEXT NOT NULL,
            trading_currency TEXT NOT NULL CHECK (trading_currency IN ('CAD', 'USD')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        INSERT INTO instruments_v2
            (id, canonical_symbol, security_name, asset_type, exchange,
             trading_currency, created_at, updated_at)
        SELECT id, canonical_symbol, security_name, asset_type, exchange,
               trading_currency, created_at, updated_at
        FROM instruments;

        DROP TABLE instruments;
        ALTER TABLE instruments_v2 RENAME TO instruments;

        COMMIT;
        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        3,
        """
        ALTER TABLE instruments ADD COLUMN manual_sector TEXT;
        ALTER TABLE instruments ADD COLUMN sector_source TEXT;
        ALTER TABLE instruments ADD COLUMN sector_source_url TEXT;
        ALTER TABLE instruments ADD COLUMN sector_as_of TEXT;
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS snaptrade_sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            connection_status TEXT NOT NULL,
            connection_permission TEXT,
            brokerage_name TEXT,
            connection_fingerprint TEXT,
            last_checked_at TEXT,
            last_attempted_sync_at TEXT,
            last_successful_sync_at TEXT,
            holdings_as_of TEXT,
            warning TEXT,
            updated_at TEXT NOT NULL
        );

        INSERT OR IGNORE INTO snaptrade_sync_state
            (id, connection_status, updated_at)
        VALUES (1, 'not_checked', CURRENT_TIMESTAMP);

        CREATE TABLE IF NOT EXISTS snaptrade_sync_previews (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            holdings_as_of TEXT,
            last_successful_sync_at TEXT,
            rows_json TEXT NOT NULL,
            changes_json TEXT NOT NULL,
            issues_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snaptrade_sync_previews_expires
            ON snaptrade_sync_previews(expires_at);
        """,
    ),
)


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.database_path
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            applied = {
                int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                connection.executescript(sql)
                connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            connection.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
