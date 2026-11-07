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
        CREATE TABLE IF NOT EXISTS instruments (
            id TEXT PRIMARY KEY,
            canonical_symbol TEXT NOT NULL UNIQUE,
            security_name TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'ETF', 'CASH')),
            exchange TEXT NOT NULL,
            manual_sector TEXT,
            sector_source TEXT,
            sector_source_url TEXT,
            sector_as_of TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS holding_snapshots (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (
                source_type IN ('manual_edit', 'manual_row_removal', 'demo')
            ),
            data_origin TEXT NOT NULL CHECK (data_origin IN ('manual', 'demo')),
            position_count INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_holding_snapshots_created
            ON holding_snapshots(created_at DESC);

        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES holding_snapshots(id) ON DELETE CASCADE,
            instrument_id TEXT NOT NULL REFERENCES instruments(id),
            account_name TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            quantity TEXT NOT NULL,
            average_cost TEXT,
            UNIQUE(snapshot_id, account_name, instrument_id)
        );

        CREATE TABLE IF NOT EXISTS price_quotes (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL REFERENCES instruments(id),
            price TEXT NOT NULL,
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

        CREATE TABLE IF NOT EXISTS valuation_snapshots (
            id TEXT PRIMARY KEY,
            holding_snapshot_id TEXT NOT NULL REFERENCES holding_snapshots(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            total_value TEXT NOT NULL,
            priced_positions INTEGER NOT NULL,
            total_positions INTEGER NOT NULL,
            position_coverage_pct TEXT NOT NULL,
            warnings_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_valuation_snapshots_created
            ON valuation_snapshots(created_at DESC);

        CREATE TABLE IF NOT EXISTS position_valuations (
            id TEXT PRIMARY KEY,
            valuation_snapshot_id TEXT NOT NULL REFERENCES valuation_snapshots(id) ON DELETE CASCADE,
            position_id TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
            price_quote_id TEXT REFERENCES price_quotes(id),
            market_value TEXT,
            unrealized_gain_loss TEXT,
            portfolio_weight TEXT,
            data_status TEXT NOT NULL,
            UNIQUE(valuation_snapshot_id, position_id)
        );

        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            activity_type TEXT NOT NULL CHECK (
                activity_type IN (
                    'BUY', 'SELL', 'DIVIDEND', 'DEPOSIT', 'WITHDRAWAL',
                    'FEE', 'INTEREST', 'WITHHOLDING_TAX', 'OTHER'
                )
            ),
            symbol TEXT,
            trade_date TEXT NOT NULL,
            quantity TEXT,
            price TEXT,
            fee TEXT,
            cash_amount TEXT,
            note TEXT NOT NULL DEFAULT '',
            data_origin TEXT NOT NULL CHECK (data_origin IN ('manual', 'demo')),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_activities_date
            ON activities(trade_date DESC);
        CREATE INDEX IF NOT EXISTS idx_activities_symbol
            ON activities(symbol, trade_date DESC);

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
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS market_symbols (
            symbol TEXT PRIMARY KEY,
            security_name TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'ETF')),
            exchange TEXT NOT NULL,
            history_fetched_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS price_bars (
            symbol TEXT NOT NULL REFERENCES market_symbols(symbol) ON DELETE CASCADE,
            bar_date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            adj_close REAL NOT NULL,
            volume INTEGER,
            PRIMARY KEY (symbol, bar_date)
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY REFERENCES market_symbols(symbol),
            position INTEGER NOT NULL,
            added_at TEXT NOT NULL
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS sec_cache (
            cache_key TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS peer_lists (
            symbol TEXT PRIMARY KEY,
            peers_json TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('SIC', 'USER')),
            sic TEXT,
            sic_description TEXT,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            body TEXT NOT NULL,
            pinned_date TEXT,
            author TEXT NOT NULL CHECK (author IN ('USER', 'CLAUDE')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notes_symbol_created
            ON notes(symbol, created_at DESC);
        """,
    ),
    (
        5,
        """
        CREATE TABLE IF NOT EXISTS exit_plans (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            target_price TEXT,
            stop_price TEXT,
            review_date TEXT,
            reasoning TEXT NOT NULL,
            proposed_by TEXT NOT NULL CHECK (proposed_by IN ('CLAUDE', 'USER')),
            status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')),
            reference_price TEXT,
            reference_date TEXT,
            note_id TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_exit_plans_symbol_created
            ON exit_plans(symbol, created_at DESC);

        ALTER TABLE review_triggers ADD COLUMN exit_plan_id TEXT;
        """,
    ),
    (
        6,
        """
        ALTER TABLE local_alerts ADD COLUMN notified_at TEXT;
        """,
    ),
    (
        7,
        """
        CREATE TABLE IF NOT EXISTS news_items (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('HEADLINE', 'FILING')),
            title TEXT NOT NULL,
            summary TEXT,
            url TEXT NOT NULL,
            publisher TEXT NOT NULL,
            published_at TEXT NOT NULL,
            positive REAL,
            neutral REAL,
            negative REAL,
            sentiment_model TEXT,
            scored_at TEXT,
            first_seen_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_news_items_symbol_published
            ON news_items(symbol, published_at DESC);

        CREATE TABLE IF NOT EXISTS news_fetches (
            symbol TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            failures_json TEXT NOT NULL DEFAULT '{}'
        );
        """,
    ),
    (
        8,
        """
        CREATE TABLE IF NOT EXISTS macro_cache (
            cache_key TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
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
