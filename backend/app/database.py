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
    (
        5,
        """
        ALTER TABLE snaptrade_sync_previews
            ADD COLUMN activities_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE snaptrade_sync_previews
            ADD COLUMN activity_summary_json TEXT NOT NULL DEFAULT '{}';

        CREATE TABLE IF NOT EXISTS brokerage_activities (
            activity_key TEXT PRIMARY KEY,
            account_fingerprint TEXT NOT NULL,
            normalized_type TEXT NOT NULL CHECK (
                normalized_type IN (
                    'BUY', 'SELL', 'DISTRIBUTION', 'DEPOSIT', 'WITHDRAWAL',
                    'FEE', 'INTEREST', 'WITHHOLDING_TAX', 'TRANSFER', 'OTHER'
                )
            ),
            symbol TEXT,
            trade_date TEXT,
            settlement_date TEXT,
            quantity TEXT,
            price TEXT,
            currency TEXT,
            fee TEXT,
            cash_amount TEXT,
            source TEXT NOT NULL,
            source_as_of TEXT,
            record_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            holding_snapshot_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_brokerage_activities_date
            ON brokerage_activities(trade_date DESC);
        CREATE INDEX IF NOT EXISTS idx_brokerage_activities_symbol
            ON brokerage_activities(symbol, trade_date DESC);

        CREATE TABLE IF NOT EXISTS brokerage_activity_revisions (
            id TEXT PRIMARY KEY,
            activity_key TEXT NOT NULL,
            record_hash TEXT NOT NULL,
            normalized_json TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            holding_snapshot_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_brokerage_activity_revisions_key
            ON brokerage_activity_revisions(activity_key, observed_at DESC);

        CREATE TABLE IF NOT EXISTS activity_coverage (
            account_fingerprint TEXT PRIMARY KEY,
            coverage_start TEXT,
            coverage_end TEXT,
            complete_initial_sync INTEGER NOT NULL CHECK (complete_initial_sync IN (0, 1)),
            source_as_of TEXT,
            last_synced_at TEXT NOT NULL,
            warning TEXT
        );

        CREATE TABLE IF NOT EXISTS investment_profiles (
            instrument_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            portfolio_role TEXT CHECK (
                portfolio_role IN ('CORE', 'DIVERSIFIER', 'INCOME', 'SPECULATIVE')
            ),
            thesis_strength INTEGER CHECK (thesis_strength BETWEEN 1 AND 5),
            why_owned TEXT NOT NULL DEFAULT '',
            supporting_evidence TEXT NOT NULL DEFAULT '',
            principal_risks TEXT NOT NULL DEFAULT '',
            invalidation_conditions TEXT NOT NULL DEFAULT '',
            maximum_weight TEXT,
            source_links_json TEXT NOT NULL DEFAULT '[]',
            last_reviewed_date TEXT,
            next_review_date TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS current_decisions (
            instrument_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (
                decision IN ('WATCH', 'HOLD', 'CONSIDER_ADD', 'CONSIDER_REDUCE', 'EXIT_CANDIDATE')
            ),
            reason TEXT NOT NULL DEFAULT '',
            decision_date TEXT NOT NULL,
            review_due_date TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decision_history (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            decision_date TEXT NOT NULL,
            previous_decision TEXT,
            new_decision TEXT NOT NULL CHECK (
                new_decision IN ('WATCH', 'HOLD', 'CONSIDER_ADD', 'CONSIDER_REDUCE', 'EXIT_CANDIDATE')
            ),
            reason TEXT NOT NULL DEFAULT '',
            claude_disposition TEXT CHECK (
                claude_disposition IN ('ACCEPTED', 'REJECTED', 'CONSIDERING')
            ),
            review_due_date TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decision_history_instrument_date
            ON decision_history(instrument_id, decision_date DESC, created_at DESC);

        CREATE TABLE IF NOT EXISTS review_triggers (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trigger_type TEXT NOT NULL CHECK (
                trigger_type IN (
                    'PRICE_BELOW', 'PRICE_ABOVE', 'CONSIDER_ADD_RANGE',
                    'CONSIDER_REDUCE_RANGE', 'DATE', 'AFTER_EARNINGS', 'THESIS_NOTE'
                )
            ),
            lower_value TEXT,
            upper_value TEXT,
            trigger_date TEXT,
            note TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            expires_at TEXT,
            state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'TRIGGERED', 'EXPIRED', 'DISMISSED')),
            created_at TEXT NOT NULL,
            triggered_at TEXT,
            observed_value TEXT,
            quote_source TEXT,
            quote_timestamp TEXT,
            frozen_holding_snapshot_id TEXT,
            frozen_valuation_snapshot_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_review_triggers_instrument_state
            ON review_triggers(instrument_id, state, created_at DESC);

        CREATE TABLE IF NOT EXISTS local_alerts (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            message TEXT NOT NULL,
            dismissed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS claude_prompts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            is_default INTEGER NOT NULL CHECK (is_default IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS claude_review_exports (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trigger_id TEXT,
            prompt_id TEXT NOT NULL,
            privacy_json TEXT NOT NULL,
            markdown_text TEXT NOT NULL,
            holdings_as_of TEXT,
            evidence_as_of TEXT,
            generated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_reviews (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            review_date TEXT NOT NULL,
            evidence_as_of TEXT,
            suggestion TEXT NOT NULL CHECK (
                suggestion IN (
                    'CONSIDER_BUY', 'HOLD', 'CONSIDER_REDUCE',
                    'CONSIDER_EXIT', 'INSUFFICIENT_DATA'
                )
            ),
            explanation TEXT NOT NULL DEFAULT '',
            bull_case TEXT NOT NULL DEFAULT '',
            bear_case TEXT NOT NULL DEFAULT '',
            principal_risks TEXT NOT NULL DEFAULT '',
            missing_information TEXT NOT NULL DEFAULT '',
            change_conditions TEXT NOT NULL DEFAULT '',
            source_links_json TEXT NOT NULL DEFAULT '[]',
            claude_model TEXT,
            disposition TEXT NOT NULL CHECK (
                disposition IN ('ACCEPTED', 'REJECTED', 'CONSIDERING')
            ),
            original_markdown TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_reviews_instrument_date
            ON ai_reviews(instrument_id, review_date DESC, created_at DESC);

        CREATE TABLE IF NOT EXISTS historical_price_observations (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            value TEXT NOT NULL,
            currency TEXT NOT NULL,
            series_type TEXT NOT NULL CHECK (
                series_type IN ('ADJUSTED_TOTAL_RETURN', 'RAW_CLOSE')
            ),
            distributions_included INTEGER NOT NULL CHECK (distributions_included IN (0, 1)),
            source TEXT NOT NULL,
            source_url TEXT,
            observed_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(instrument_id, observation_date, series_type, source)
        );

        CREATE TABLE IF NOT EXISTS etf_evidence_profiles (
            id TEXT PRIMARY KEY,
            instrument_id TEXT,
            symbol TEXT NOT NULL,
            issuer TEXT NOT NULL,
            source_url TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            data_as_of TEXT NOT NULL,
            verified_on TEXT NOT NULL,
            method TEXT NOT NULL,
            coverage_pct TEXT NOT NULL,
            mer_pct TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_etf_evidence_symbol_date
            ON etf_evidence_profiles(symbol, data_as_of DESC, verified_on DESC);

        CREATE TABLE IF NOT EXISTS etf_evidence_holdings (
            id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL REFERENCES etf_evidence_profiles(id) ON DELETE CASCADE,
            holding_key TEXT NOT NULL,
            holding_name TEXT NOT NULL,
            weight TEXT NOT NULL,
            sector TEXT,
            country TEXT,
            economic_currency TEXT,
            UNIQUE(evidence_id, holding_key)
        );
        """,
    ),
    (
        6,
        """
        ALTER TABLE holding_snapshots ADD COLUMN data_origin TEXT CHECK (
            data_origin IN ('legacy', 'snaptrade') OR data_origin IS NULL
        );

        UPDATE holding_snapshots
        SET data_origin = CASE
            WHEN source_type = 'snaptrade_read_sync' THEN 'snaptrade'
            WHEN source_type != 'manual_row_removal' THEN 'legacy'
            ELSE NULL
        END;

        UPDATE holding_snapshots
        SET data_origin = (
            SELECT CASE
                WHEN parent.source_type = 'snaptrade_read_sync' THEN 'snaptrade'
                ELSE 'legacy'
            END
            FROM holding_snapshots AS parent
            WHERE parent.imported_at < holding_snapshots.imported_at
              AND parent.source_type != 'manual_row_removal'
            ORDER BY parent.imported_at DESC
            LIMIT 1
        )
        WHERE source_type = 'manual_row_removal';
        """,
    ),
    (
        7,
        """
        -- Repair installations where migration 5 was recorded before the
        -- activity-revisions table was added to that migration's source.
        CREATE TABLE IF NOT EXISTS brokerage_activity_revisions (
            id TEXT PRIMARY KEY,
            activity_key TEXT NOT NULL,
            record_hash TEXT NOT NULL,
            normalized_json TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            holding_snapshot_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_brokerage_activity_revisions_key
            ON brokerage_activity_revisions(activity_key, observed_at DESC);
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
