"""Persistence operations for holdings, prices, valuations, and activities."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from app.database import Database

ACTIVITY_TYPES = (
    "BUY",
    "SELL",
    "DIVIDEND",
    "DEPOSIT",
    "WITHDRAWAL",
    "FEE",
    "INTEREST",
    "WITHHOLDING_TAX",
    "OTHER",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class PortfolioRepository:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()

    @staticmethod
    def _upsert_instrument(connection: sqlite3.Connection, row: dict[str, Any], now: str) -> str:
        instrument = connection.execute(
            "SELECT id FROM instruments WHERE canonical_symbol = ?",
            (row["canonical_symbol"],),
        ).fetchone()
        if instrument is None:
            instrument_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO instruments
                    (id, canonical_symbol, security_name, asset_type, exchange,
                     manual_sector, sector_source, sector_as_of, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instrument_id,
                    row["canonical_symbol"],
                    row["security_name"],
                    row["asset_type"],
                    row["exchange"],
                    row.get("manual_sector"),
                    "User classification" if row.get("manual_sector") else None,
                    now[:10] if row.get("manual_sector") else None,
                    now,
                    now,
                ),
            )
            return instrument_id
        connection.execute(
            """
            UPDATE instruments
            SET security_name = ?, asset_type = ?, exchange = ?, updated_at = ?
            WHERE id = ?
            """,
            (row["security_name"], row["asset_type"], row["exchange"], now, instrument["id"]),
        )
        return str(instrument["id"])

    def instrument(self, instrument_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
        return dict(row) if row else None

    def instrument_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM instruments WHERE canonical_symbol = ?", (symbol,)
            ).fetchone()
        return dict(row) if row else None

    def ensure_instrument(self, identity: dict[str, Any]) -> str:
        """Return the instrument for a symbol, creating it for tickers that are not held."""
        existing = self.instrument_by_symbol(identity["canonical_symbol"])
        if existing is not None:
            return str(existing["id"])
        with self.database.transaction() as connection:
            return self._upsert_instrument(connection, identity, utc_now())

    def create_snapshot(
        self,
        rows: list[dict[str, Any]],
        *,
        source_type: str,
        data_origin: str,
    ) -> str:
        """Store a complete, immutable holdings snapshot from normalized rows."""
        snapshot_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO holding_snapshots
                    (id, created_at, source_type, data_origin, position_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, now, source_type, data_origin, len(rows)),
            )
            for row_number, row in enumerate(rows, start=1):
                instrument_id = self._upsert_instrument(connection, row, now)
                connection.execute(
                    """
                    INSERT INTO positions
                        (id, snapshot_id, instrument_id, account_name, row_number,
                         quantity, average_cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        snapshot_id,
                        instrument_id,
                        row["account_name"],
                        row_number,
                        row["quantity"],
                        row.get("average_cost"),
                    ),
                )
        return snapshot_id

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM holding_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def latest_holding_snapshot_id(self) -> str | None:
        snapshot = self.latest_snapshot()
        return str(snapshot["id"]) if snapshot else None

    def snapshot_count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM holding_snapshots").fetchone()[0])

    def positions_for_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id AS position_id, p.quantity, p.average_cost, p.account_name,
                    p.row_number,
                    i.id AS instrument_id, i.canonical_symbol, i.security_name,
                    i.asset_type, i.exchange, i.manual_sector, i.sector_source,
                    i.sector_source_url, i.sector_as_of
                FROM positions p
                JOIN instruments i ON i.id = p.instrument_id
                WHERE p.snapshot_id = ?
                ORDER BY p.row_number
                """,
                (snapshot_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _current_rows(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        latest = self.latest_snapshot()
        if latest is None:
            return None, []
        return latest, self.positions_for_snapshot(str(latest["id"]))

    def create_snapshot_with_position(self, row: dict[str, Any]) -> str:
        """Add a position, or replace the same symbol in the same account, in a new snapshot."""
        latest, current = self._current_rows()
        replaced = False
        rows: list[dict[str, Any]] = []
        for existing in current:
            if (
                existing["canonical_symbol"] == row["canonical_symbol"]
                and existing["account_name"] == row["account_name"]
            ):
                rows.append(row)
                replaced = True
            else:
                rows.append(existing)
        if not replaced:
            rows.append(row)
        origin = str(latest["data_origin"]) if latest else "manual"
        return self.create_snapshot(rows, source_type="manual_edit", data_origin=origin)

    def create_snapshot_without_position(self, position_id: str) -> tuple[str, str]:
        """Create a new current snapshot without one selected position.

        Earlier snapshots and their valuations remain unchanged for historical
        traceability. No brokerage action is represented or performed.
        """
        latest, current = self._current_rows()
        if latest is None:
            raise ValueError("No holdings snapshot exists")
        target = next((row for row in current if row["position_id"] == position_id), None)
        if target is None:
            with self.database.connect() as connection:
                known = connection.execute(
                    "SELECT 1 FROM positions WHERE id = ?", (position_id,)
                ).fetchone()
            if known is None:
                raise KeyError("Holding row was not found")
            raise ValueError("The portfolio changed; select the current row and try again")
        remaining = [row for row in current if row["position_id"] != position_id]
        snapshot_id = self.create_snapshot(
            remaining,
            source_type="manual_row_removal",
            data_origin=str(latest["data_origin"]),
        )
        return snapshot_id, str(target["canonical_symbol"])

    def update_instrument_sector(self, instrument_id: str, sector: str | None) -> None:
        """Store a user-controlled direct-security classification."""
        now = utc_now()
        with self.database.transaction() as connection:
            instrument = connection.execute(
                "SELECT asset_type FROM instruments WHERE id = ?", (instrument_id,)
            ).fetchone()
            if instrument is None:
                raise KeyError("Instrument was not found")
            if instrument["asset_type"] == "ETF":
                raise ValueError("ETF sectors come from dated issuer holdings evidence")
            if instrument["asset_type"] == "CASH":
                raise ValueError("Cash is always classified as Cash")
            connection.execute(
                """
                UPDATE instruments
                SET manual_sector = ?, sector_source = ?, sector_source_url = NULL,
                    sector_as_of = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    sector,
                    "User classification" if sector else None,
                    now[:10] if sector else None,
                    now,
                    instrument_id,
                ),
            )

    def save_quote(self, instrument_id: str, quote: dict[str, Any]) -> str:
        quote_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO price_quotes
                    (id, instrument_id, price, observed_at, fetched_at,
                     source, source_url, quote_status, delay_minutes, stale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    instrument_id,
                    quote["price"],
                    quote["observed_at"],
                    quote["fetched_at"],
                    quote["source"],
                    quote.get("source_url"),
                    quote["quote_status"],
                    quote.get("delay_minutes"),
                    int(bool(quote["stale"])),
                ),
            )
        return quote_id

    def latest_quote(self, instrument_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM price_quotes
                WHERE instrument_id = ? ORDER BY fetched_at DESC LIMIT 1
                """,
                (instrument_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_valuation(
        self,
        *,
        holding_snapshot_id: str,
        total_value: str,
        priced_positions: int,
        total_positions: int,
        coverage_pct: str,
        warnings: list[str],
        positions: list[dict[str, Any]],
    ) -> str:
        valuation_id = uuid.uuid4().hex
        created_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO valuation_snapshots
                    (id, holding_snapshot_id, created_at, total_value, priced_positions,
                     total_positions, position_coverage_pct, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    valuation_id,
                    holding_snapshot_id,
                    created_at,
                    total_value,
                    priced_positions,
                    total_positions,
                    coverage_pct,
                    _json(warnings),
                ),
            )
            for row in positions:
                connection.execute(
                    """
                    INSERT INTO position_valuations
                        (id, valuation_snapshot_id, position_id, price_quote_id,
                         market_value, unrealized_gain_loss, portfolio_weight, data_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        valuation_id,
                        row["position_id"],
                        row.get("price_quote_id"),
                        row.get("market_value"),
                        row.get("unrealized_gain_loss"),
                        row.get("portfolio_weight"),
                        row["data_status"],
                    ),
                )
        return valuation_id

    def latest_portfolio(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            valuation = connection.execute(
                """
                SELECT v.*, h.created_at AS snapshot_created_at, h.data_origin
                FROM valuation_snapshots v
                JOIN holding_snapshots h ON h.id = v.holding_snapshot_id
                ORDER BY v.created_at DESC LIMIT 1
                """
            ).fetchone()
            if valuation is None:
                return None
            rows = connection.execute(
                """
                SELECT
                    pv.*, p.quantity, p.average_cost, p.account_name,
                    i.id AS instrument_id, i.canonical_symbol, i.security_name,
                    i.asset_type, i.exchange, i.manual_sector, i.sector_source,
                    i.sector_source_url, i.sector_as_of,
                    q.price, q.observed_at AS price_timestamp,
                    q.fetched_at AS price_fetched_at, q.source AS price_source,
                    q.source_url AS price_source_url, q.quote_status, q.delay_minutes,
                    q.stale AS price_stale
                FROM position_valuations pv
                JOIN positions p ON p.id = pv.position_id
                JOIN instruments i ON i.id = p.instrument_id
                LEFT JOIN price_quotes q ON q.id = pv.price_quote_id
                WHERE pv.valuation_snapshot_id = ?
                ORDER BY CAST(pv.market_value AS REAL) DESC, i.canonical_symbol
                """,
                (valuation["id"],),
            ).fetchall()
        return {
            "valuation_snapshot_id": valuation["id"],
            "holding_snapshot_id": valuation["holding_snapshot_id"],
            "created_at": valuation["created_at"],
            "snapshot_created_at": valuation["snapshot_created_at"],
            "data_origin": valuation["data_origin"],
            "total_value": valuation["total_value"],
            "priced_positions": valuation["priced_positions"],
            "total_positions": valuation["total_positions"],
            "position_coverage_pct": valuation["position_coverage_pct"],
            "warnings": json.loads(valuation["warnings_json"]),
            "holdings": [dict(row) for row in rows],
        }

    def portfolio_history(self, limit: int = 180) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1_000))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, holding_snapshot_id, created_at, total_value,
                       priced_positions, total_positions, position_coverage_pct
                FROM valuation_snapshots ORDER BY created_at DESC LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return list(reversed([dict(row) for row in rows]))

    def add_activity(self, values: dict[str, Any], *, data_origin: str = "manual") -> str:
        if values["activity_type"] not in ACTIVITY_TYPES:
            raise ValueError("Unsupported activity type")
        activity_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO activities
                    (id, activity_type, symbol, trade_date, quantity, price, fee,
                     cash_amount, note, data_origin, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    values["activity_type"],
                    values.get("symbol"),
                    values["trade_date"],
                    values.get("quantity"),
                    values.get("price"),
                    values.get("fee"),
                    values.get("cash_amount"),
                    values.get("note") or "",
                    data_origin,
                    utc_now(),
                ),
            )
        return activity_id

    def activity_count(self, data_origin: str) -> int:
        with self.database.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM activities WHERE data_origin = ?", (data_origin,)
                ).fetchone()[0]
            )

    def delete_activity(self, activity_id: str) -> None:
        with self.database.transaction() as connection:
            deleted = connection.execute("DELETE FROM activities WHERE id = ?", (activity_id,)).rowcount
        if not deleted:
            raise KeyError("Activity was not found")

    def activities_view(
        self,
        *,
        activity_type: str | None = None,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if activity_type:
            normalized = activity_type.strip().upper()
            if normalized not in ACTIVITY_TYPES:
                raise ValueError("Unsupported activity filter")
            clauses.append("activity_type = ?")
            parameters.append(normalized)
        if symbol:
            clauses.append("symbol LIKE ?")
            parameters.append(f"%{symbol.strip().upper()}%")
        if start_date:
            clauses.append("trade_date >= ?")
            parameters.append(start_date[:10])
        if end_date:
            clauses.append("trade_date <= ?")
            parameters.append(end_date[:10])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 5_000))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, activity_type, symbol, trade_date, quantity, price, fee,
                       cash_amount, note, data_origin, created_at
                FROM activities
                """
                + where
                + " ORDER BY trade_date DESC, created_at DESC LIMIT ?",
                (*parameters, safe_limit),
            ).fetchall()
            bounds = connection.execute(
                "SELECT MIN(trade_date) AS start, MAX(trade_date) AS end, COUNT(*) AS total FROM activities"
            ).fetchone()
        warnings: list[str] = []
        if not bounds["total"]:
            warnings.append("No activities have been recorded.")
        return {
            "activities": [dict(row) for row in rows],
            "coverage": {"start": bounds["start"], "end": bounds["end"], "count": bounds["total"]},
            "warnings": warnings,
            "source": "Manually recorded activity ledger",
        }

    def delete_portfolio_data(self) -> int:
        """Delete holdings, valuations, quotes, and activities; keep the journal and instruments."""
        with self.database.transaction() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM holding_snapshots").fetchone()[0])
            connection.execute("DELETE FROM position_valuations")
            connection.execute("DELETE FROM valuation_snapshots")
            connection.execute("DELETE FROM positions")
            connection.execute("DELETE FROM holding_snapshots")
            connection.execute("DELETE FROM price_quotes")
            connection.execute("DELETE FROM activities")
        return count
