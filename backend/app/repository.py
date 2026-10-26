"""Persistence operations for imports, holdings, prices, and valuations."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database import Database


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class PortfolioRepository:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()

    def has_import_hash(self, source_hash: str) -> bool:
        with self.database.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM holding_snapshots WHERE source_file_hash = ? LIMIT 1",
                    (source_hash,),
                ).fetchone()
                is not None
            )

    def create_draft(
        self,
        *,
        source_hash: str,
        rows: list[dict[str, Any]],
        source_as_of: str | None,
        issues: list[dict[str, Any]],
        ignored_columns: list[str],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        draft_id = uuid.uuid4().hex
        expires = now + timedelta(hours=2)
        payload = {"rows": rows, "source_as_of": source_as_of}
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM import_drafts WHERE expires_at < ?", (now.isoformat(),))
            connection.execute(
                """
                INSERT INTO import_drafts
                    (id, created_at, expires_at, source_file_hash, rows_json,
                     issues_json, ignored_columns_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    now.isoformat(),
                    expires.isoformat(),
                    source_hash,
                    _json(payload),
                    _json(issues),
                    _json(ignored_columns),
                ),
            )
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM import_drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError("Import preview was not found or has expired")
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
            self.delete_draft(draft_id)
            raise KeyError("Import preview was not found or has expired")
        payload = json.loads(row["rows_json"])
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "source_file_hash": row["source_file_hash"],
            "rows": payload["rows"],
            "source_as_of": payload.get("source_as_of"),
            "issues": json.loads(row["issues_json"]),
            "ignored_columns": json.loads(row["ignored_columns_json"]),
        }

    def update_draft(
        self,
        draft_id: str,
        *,
        rows: list[dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        payload = {"rows": rows, "source_as_of": draft["source_as_of"]}
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE import_drafts SET rows_json = ?, issues_json = ? WHERE id = ?",
                (_json(payload), _json(issues), draft_id),
            )
        return self.get_draft(draft_id)

    def delete_draft(self, draft_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM import_drafts WHERE id = ?", (draft_id,))

    def snaptrade_state(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM snaptrade_sync_state WHERE id = 1").fetchone()
        return dict(row) if row else {"connection_status": "not_checked"}

    def update_snaptrade_state(self, **fields: Any) -> dict[str, Any]:
        allowed = {
            "connection_status",
            "connection_permission",
            "brokerage_name",
            "connection_fingerprint",
            "last_checked_at",
            "last_attempted_sync_at",
            "last_successful_sync_at",
            "holdings_as_of",
            "warning",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.database.transaction() as connection:
            connection.execute(
                f"UPDATE snaptrade_sync_state SET {assignments} WHERE id = 1",  # noqa: S608
                (*updates.values(),),
            )
        return self.snaptrade_state()

    def create_snaptrade_preview(
        self,
        *,
        rows: list[dict[str, Any]],
        changes: dict[str, Any],
        issues: list[dict[str, Any]],
        activities: list[dict[str, Any]] | None = None,
        activity_summary: dict[str, Any] | None = None,
        holdings_as_of: str | None,
        last_successful_sync_at: str | None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        preview_id = uuid.uuid4().hex
        expires_at = now + timedelta(minutes=30)
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM snaptrade_sync_previews WHERE expires_at < ?", (now.isoformat(),)
            )
            connection.execute(
                """
                INSERT INTO snaptrade_sync_previews
                    (id, created_at, expires_at, holdings_as_of,
                     last_successful_sync_at, rows_json, changes_json, issues_json,
                     activities_json, activity_summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview_id,
                    now.isoformat(),
                    expires_at.isoformat(),
                    holdings_as_of,
                    last_successful_sync_at,
                    _json(rows),
                    _json(changes),
                    _json(issues),
                    _json(activities or []),
                    _json(activity_summary or {}),
                ),
            )
        return self.snaptrade_preview(preview_id)

    def snaptrade_preview(self, preview_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM snaptrade_sync_previews WHERE id = ?", (preview_id,)
            ).fetchone()
        if row is None:
            raise KeyError("Synchronization preview was not found or has expired")
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
            self.delete_snaptrade_preview(preview_id)
            raise KeyError("Synchronization preview was not found or has expired")
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "holdings_as_of": row["holdings_as_of"],
            "last_successful_sync_at": row["last_successful_sync_at"],
            "rows": json.loads(row["rows_json"]),
            "changes": json.loads(row["changes_json"]),
            "issues": json.loads(row["issues_json"]),
            "activities": json.loads(row["activities_json"]),
            "activity_summary": json.loads(row["activity_summary_json"]),
        }

    def brokerage_activity_hashes(self, keys: list[str]) -> dict[str, str]:
        """Return stored normalized hashes without exposing brokerage identifiers."""
        if not keys:
            return {}
        unique_keys = list(dict.fromkeys(keys))
        placeholders = ",".join("?" for _ in unique_keys)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT activity_key, record_hash FROM brokerage_activities "  # noqa: S608
                f"WHERE activity_key IN ({placeholders})",
                unique_keys,
            ).fetchall()
        return {str(row["activity_key"]): str(row["record_hash"]) for row in rows}

    def activity_coverage_for(self, account_fingerprint: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM activity_coverage WHERE account_fingerprint = ?",
                (account_fingerprint,),
            ).fetchone()
        return dict(row) if row else None

    def latest_snaptrade_preview(self) -> dict[str, Any] | None:
        """Return the newest unexpired preview so the UI can recover after navigation."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM snaptrade_sync_previews
                WHERE expires_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (datetime.now(UTC).isoformat(),),
            ).fetchone()
        if row is None:
            return None
        try:
            return self.snaptrade_preview(str(row["id"]))
        except KeyError:
            return None

    def delete_snaptrade_preview(self, preview_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM snaptrade_sync_previews WHERE id = ?", (preview_id,))

    def persist_snaptrade_preview(
        self,
        preview_id: str,
        *,
        rows_override: list[dict[str, Any]] | None = None,
        issues_override: list[dict[str, Any]] | None = None,
    ) -> str:
        preview = self.snaptrade_preview(preview_id)
        rows = rows_override if rows_override is not None else preview["rows"]
        issues = issues_override if issues_override is not None else preview["issues"]
        activities = preview.get("activities") or []
        activity_summary = preview.get("activity_summary") or {}
        if any(issue["severity"] == "error" for issue in issues):
            raise ValueError("Resolve every synchronization error before applying this snapshot")
        snapshot_id = uuid.uuid4().hex
        applied_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO holding_snapshots
                    (id, imported_at, source_type, source_file_hash, source_as_of,
                     position_count, data_origin)
                VALUES (?, ?, 'snaptrade_read_sync', ?, ?, ?, 'snaptrade')
                """,
                (
                    snapshot_id,
                    applied_at,
                    f"snaptrade-preview:{preview_id}",
                    preview["holdings_as_of"],
                    len(rows),
                ),
            )
            for row in rows:
                account = connection.execute(
                    "SELECT id FROM accounts WHERE source_fingerprint = ?",
                    (row["account_fingerprint"],),
                ).fetchone()
                if account is None:
                    account_id = uuid.uuid4().hex
                    alias = row["account_alias"]
                    alias_owner = connection.execute(
                        "SELECT source_fingerprint FROM accounts WHERE alias = ?", (alias,)
                    ).fetchone()
                    if alias_owner is not None:
                        alias = f"{row['account_type']}-{row['account_fingerprint'][:8].upper()}"
                    connection.execute(
                        """
                        INSERT INTO accounts
                            (id, source_fingerprint, alias, account_type, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            account_id,
                            row["account_fingerprint"],
                            alias,
                            row["account_type"],
                            applied_at,
                        ),
                    )
                else:
                    account_id = account["id"]

                instrument = connection.execute(
                    "SELECT * FROM instruments WHERE canonical_symbol = ?",
                    (row["canonical_symbol"],),
                ).fetchone()
                if instrument is None:
                    instrument_id = uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO instruments
                            (id, canonical_symbol, security_name, asset_type, exchange,
                             trading_currency, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            instrument_id,
                            row["canonical_symbol"],
                            row["security_name"],
                            row["asset_type"],
                            row["exchange"],
                            row["trading_currency"],
                            applied_at,
                            applied_at,
                        ),
                    )
                else:
                    instrument_id = instrument["id"]
                    conflicts = (
                        instrument["exchange"] != row["exchange"]
                        or instrument["trading_currency"] != row["trading_currency"]
                        or instrument["asset_type"] != row["asset_type"]
                    )
                    if conflicts:
                        raise ValueError(
                            f"Stored identity conflicts with {row['canonical_symbol']}; "
                            "the synchronization was not applied"
                        )
                    connection.execute(
                        "UPDATE instruments SET security_name = ?, updated_at = ? WHERE id = ?",
                        (row["security_name"], applied_at, instrument_id),
                    )

                connection.execute(
                    """
                    INSERT INTO positions
                        (id, snapshot_id, account_id, instrument_id, source_row_number,
                         quantity, average_cost, imported_price, imported_market_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        uuid.uuid4().hex,
                        snapshot_id,
                        account_id,
                        instrument_id,
                        row["row_number"],
                        row["quantity"],
                        row["average_cost"],
                    ),
                )

            for activity in activities:
                existing = connection.execute(
                    "SELECT record_hash FROM brokerage_activities WHERE activity_key = ?",
                    (activity["activity_key"],),
                ).fetchone()
                if existing is None or existing["record_hash"] != activity["record_hash"]:
                    connection.execute(
                        """
                        INSERT INTO brokerage_activity_revisions
                            (id, activity_key, record_hash, normalized_json, observed_at,
                             holding_snapshot_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            uuid.uuid4().hex,
                            activity["activity_key"],
                            activity["record_hash"],
                            _json(
                                {
                                    key: value
                                    for key, value in activity.items()
                                    if key not in {"account_fingerprint"}
                                }
                            ),
                            applied_at,
                            snapshot_id,
                        ),
                    )
                connection.execute(
                    """
                    INSERT INTO brokerage_activities
                        (activity_key, account_fingerprint, normalized_type, symbol,
                         trade_date, settlement_date, quantity, price, currency, fee,
                         cash_amount, source, source_as_of, record_hash, first_seen_at,
                         last_seen_at, holding_snapshot_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(activity_key) DO UPDATE SET
                        normalized_type = excluded.normalized_type,
                        symbol = excluded.symbol,
                        trade_date = excluded.trade_date,
                        settlement_date = excluded.settlement_date,
                        quantity = excluded.quantity,
                        price = excluded.price,
                        currency = excluded.currency,
                        fee = excluded.fee,
                        cash_amount = excluded.cash_amount,
                        source_as_of = excluded.source_as_of,
                        record_hash = excluded.record_hash,
                        last_seen_at = excluded.last_seen_at,
                        holding_snapshot_id = excluded.holding_snapshot_id
                    """,
                    (
                        activity["activity_key"],
                        activity["account_fingerprint"],
                        activity["normalized_type"],
                        activity.get("symbol"),
                        activity.get("trade_date"),
                        activity.get("settlement_date"),
                        activity.get("quantity"),
                        activity.get("price"),
                        activity.get("currency"),
                        activity.get("fee"),
                        activity.get("cash_amount"),
                        "SnapTrade daily activities",
                        activity.get("source_as_of"),
                        activity["record_hash"],
                        applied_at,
                        applied_at,
                        snapshot_id,
                    ),
                )

            for coverage in activity_summary.get("accounts", []):
                connection.execute(
                    """
                    INSERT INTO activity_coverage
                        (account_fingerprint, coverage_start, coverage_end,
                         complete_initial_sync, source_as_of, last_synced_at, warning)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_fingerprint) DO UPDATE SET
                        coverage_start = excluded.coverage_start,
                        coverage_end = excluded.coverage_end,
                        complete_initial_sync = excluded.complete_initial_sync,
                        source_as_of = excluded.source_as_of,
                        last_synced_at = excluded.last_synced_at,
                        warning = excluded.warning
                    """,
                    (
                        coverage["account_fingerprint"],
                        coverage.get("coverage_start"),
                        coverage.get("coverage_end"),
                        int(bool(coverage.get("complete_initial_sync"))),
                        coverage.get("source_as_of"),
                        applied_at,
                        coverage.get("warning"),
                    ),
                )
            connection.execute("DELETE FROM snaptrade_sync_previews WHERE id = ?", (preview_id,))
        return snapshot_id

    def delete_local_snaptrade_data(self) -> int:
        """Delete SnapTrade-derived local data while retaining legacy snapshots."""
        with self.database.transaction() as connection:
            snapshot_rows = connection.execute(
                "SELECT id FROM holding_snapshots WHERE data_origin = 'snaptrade'"
            ).fetchall()
            snapshot_ids = [row["id"] for row in snapshot_rows]
            if snapshot_ids:
                placeholders = ",".join("?" for _ in snapshot_ids)
                activity_keys = [
                    str(row["activity_key"])
                    for row in connection.execute(
                        f"SELECT activity_key FROM brokerage_activities "  # noqa: S608
                        f"WHERE holding_snapshot_id IN ({placeholders})",
                        snapshot_ids,
                    ).fetchall()
                ]
                if activity_keys:
                    activity_placeholders = ",".join("?" for _ in activity_keys)
                    connection.execute(
                        f"DELETE FROM brokerage_activity_revisions "  # noqa: S608
                        f"WHERE activity_key IN ({activity_placeholders})",
                        activity_keys,
                    )
                connection.execute(
                    f"DELETE FROM brokerage_activities "  # noqa: S608
                    f"WHERE holding_snapshot_id IN ({placeholders})",
                    snapshot_ids,
                )
                valuation_rows = connection.execute(
                    f"SELECT id FROM valuation_snapshots "  # noqa: S608
                    f"WHERE holding_snapshot_id IN ({placeholders})",
                    snapshot_ids,
                ).fetchall()
                valuation_ids = [row["id"] for row in valuation_rows]
                if valuation_ids:
                    valuation_placeholders = ",".join("?" for _ in valuation_ids)
                    connection.execute(
                        f"DELETE FROM position_valuations "  # noqa: S608
                        f"WHERE valuation_snapshot_id IN ({valuation_placeholders})",
                        valuation_ids,
                    )
                    connection.execute(
                        f"DELETE FROM valuation_snapshots "  # noqa: S608
                        f"WHERE id IN ({valuation_placeholders})",
                        valuation_ids,
                    )
                connection.execute(
                    f"DELETE FROM holding_snapshots WHERE id IN ({placeholders})",  # noqa: S608
                    snapshot_ids,
                )
            connection.execute("DELETE FROM activity_coverage")
            connection.execute("DELETE FROM snaptrade_sync_previews")
            connection.execute("DELETE FROM accounts WHERE id NOT IN (SELECT account_id FROM positions)")
            connection.execute(
                """
                UPDATE snaptrade_sync_state
                SET connection_status = 'not_checked', connection_permission = NULL,
                    brokerage_name = NULL, connection_fingerprint = NULL,
                    last_checked_at = NULL, last_attempted_sync_at = NULL,
                    last_successful_sync_at = NULL, holdings_as_of = NULL,
                    warning = NULL, updated_at = ?
                WHERE id = 1
                """,
                (utc_now(),),
            )
        return len(snapshot_ids)

    def persist_draft(self, draft_id: str) -> str:
        draft = self.get_draft(draft_id)
        if any(issue["severity"] == "error" for issue in draft["issues"]):
            raise ValueError("Resolve all import errors before accepting this portfolio")
        snapshot_id = uuid.uuid4().hex
        imported_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO holding_snapshots
                    (id, imported_at, source_type, source_file_hash, source_as_of,
                     position_count, data_origin)
                VALUES (?, ?, 'wealthsimple_holdings_csv', ?, ?, ?, 'legacy')
                """,
                (
                    snapshot_id,
                    imported_at,
                    draft["source_file_hash"],
                    draft["source_as_of"],
                    len(draft["rows"]),
                ),
            )
            for row in draft["rows"]:
                account = connection.execute(
                    "SELECT id FROM accounts WHERE source_fingerprint = ?",
                    (row["account_fingerprint"],),
                ).fetchone()
                if account is None:
                    account_id = uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO accounts
                            (id, source_fingerprint, alias, account_type, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            account_id,
                            row["account_fingerprint"],
                            row["account_alias"],
                            row["account_type"],
                            imported_at,
                        ),
                    )
                else:
                    account_id = account["id"]

                instrument = connection.execute(
                    "SELECT * FROM instruments WHERE canonical_symbol = ?",
                    (row["canonical_symbol"],),
                ).fetchone()
                if instrument is None:
                    instrument_id = uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO instruments
                            (id, canonical_symbol, security_name, asset_type, exchange,
                             trading_currency, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            instrument_id,
                            row["canonical_symbol"],
                            row["security_name"],
                            row["asset_type"],
                            row["exchange"],
                            row["trading_currency"],
                            imported_at,
                            imported_at,
                        ),
                    )
                else:
                    instrument_id = instrument["id"]
                    conflicts = (
                        instrument["exchange"] != row["exchange"]
                        or instrument["trading_currency"] != row["trading_currency"]
                        or instrument["asset_type"] != row["asset_type"]
                    )
                    if conflicts:
                        raise ValueError(
                            f"Stored identity conflicts with {row['canonical_symbol']}; "
                            "cancel and review the exchange, currency, and security type"
                        )
                    connection.execute(
                        "UPDATE instruments SET security_name = ?, updated_at = ? WHERE id = ?",
                        (row["security_name"], imported_at, instrument_id),
                    )

                connection.execute(
                    """
                    INSERT INTO positions
                        (id, snapshot_id, account_id, instrument_id, source_row_number,
                         quantity, average_cost, imported_price, imported_market_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        snapshot_id,
                        account_id,
                        instrument_id,
                        row["row_number"],
                        row["quantity"],
                        row["average_cost"],
                        row["imported_price"],
                        row["imported_market_value"],
                    ),
                )
            connection.execute("DELETE FROM import_drafts WHERE id = ?", (draft_id,))
        return snapshot_id

    def latest_holding_snapshot_id(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM holding_snapshots ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
        return str(row["id"]) if row else None

    def positions_for_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id AS position_id, p.quantity, p.average_cost,
                    p.imported_price, p.imported_market_value,
                    a.alias AS account_alias, a.account_type,
                    i.id AS instrument_id, i.canonical_symbol, i.security_name,
                    i.asset_type, i.exchange, i.trading_currency,
                    i.manual_sector, i.sector_source, i.sector_source_url,
                    i.sector_as_of
                FROM positions p
                JOIN accounts a ON a.id = p.account_id
                JOIN instruments i ON i.id = p.instrument_id
                WHERE p.snapshot_id = ?
                ORDER BY i.canonical_symbol, a.alias
                """,
                (snapshot_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_snapshot_without_position(self, position_id: str) -> tuple[str, str]:
        """Create a new current snapshot without one selected position.

        Imported snapshots and their valuations remain unchanged for historical
        traceability. The selected position is copied out of the new snapshot;
        no brokerage action is represented or performed.
        """
        snapshot_id = uuid.uuid4().hex
        imported_at = utc_now()
        with self.database.transaction() as connection:
            latest = connection.execute(
                "SELECT * FROM holding_snapshots ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                raise ValueError("No accepted holdings snapshot exists")

            target = connection.execute(
                """
                SELECT p.snapshot_id, i.canonical_symbol
                FROM positions p
                JOIN instruments i ON i.id = p.instrument_id
                WHERE p.id = ?
                """,
                (position_id,),
            ).fetchone()
            if target is None:
                raise KeyError("Holding row was not found")
            if target["snapshot_id"] != latest["id"]:
                raise ValueError("The portfolio changed; select the current row and try again")

            remaining = connection.execute(
                """
                SELECT account_id, instrument_id, source_row_number, quantity,
                       average_cost, imported_price, imported_market_value
                FROM positions
                WHERE snapshot_id = ? AND id != ?
                ORDER BY source_row_number
                """,
                (latest["id"], position_id),
            ).fetchall()
            parent_origin = str(latest["data_origin"] or "legacy")
            connection.execute(
                """
                INSERT INTO holding_snapshots
                    (id, imported_at, source_type, source_file_hash, source_as_of,
                     position_count, data_origin)
                VALUES (?, ?, 'manual_row_removal', ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    imported_at,
                    f"manual-row-removal:{snapshot_id}",
                    latest["source_as_of"],
                    len(remaining),
                    parent_origin,
                ),
            )
            for row in remaining:
                connection.execute(
                    """
                    INSERT INTO positions
                        (id, snapshot_id, account_id, instrument_id, source_row_number,
                         quantity, average_cost, imported_price, imported_market_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        snapshot_id,
                        row["account_id"],
                        row["instrument_id"],
                        row["source_row_number"],
                        row["quantity"],
                        row["average_cost"],
                        row["imported_price"],
                        row["imported_market_value"],
                    ),
                )
        return snapshot_id, str(target["canonical_symbol"])

    def update_instrument_sector(self, instrument_id: str, sector: str | None) -> None:
        """Store a user-controlled direct-security classification outside portfolio imports."""
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
                    (id, instrument_id, price, currency, observed_at, fetched_at,
                     source, source_url, quote_status, delay_minutes, stale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    instrument_id,
                    quote["price"],
                    quote["currency"],
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

    def save_fx(self, rate: dict[str, Any]) -> str:
        rate_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO fx_rates
                    (id, base_currency, quote_currency, rate, observed_at, fetched_at,
                     source, source_url, stale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rate_id,
                    rate["base_currency"],
                    rate["quote_currency"],
                    rate["rate"],
                    rate["observed_at"],
                    rate["fetched_at"],
                    rate["source"],
                    rate.get("source_url"),
                    int(bool(rate["stale"])),
                ),
            )
        return rate_id

    def latest_fx(self, base: str = "USD", quote: str = "CAD") -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM fx_rates
                WHERE base_currency = ? AND quote_currency = ?
                ORDER BY fetched_at DESC LIMIT 1
                """,
                (base, quote),
            ).fetchone()
        return dict(row) if row else None

    def save_valuation(
        self,
        *,
        holding_snapshot_id: str,
        total_cad: str,
        priced_positions: int,
        total_positions: int,
        coverage_pct: str,
        fx_rate_id: str | None,
        warnings: list[str],
        positions: list[dict[str, Any]],
    ) -> str:
        valuation_id = uuid.uuid4().hex
        created_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO valuation_snapshots
                    (id, holding_snapshot_id, created_at, total_cad, priced_positions,
                     total_positions, position_coverage_pct, fx_rate_id, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    valuation_id,
                    holding_snapshot_id,
                    created_at,
                    total_cad,
                    priced_positions,
                    total_positions,
                    coverage_pct,
                    fx_rate_id,
                    _json(warnings),
                ),
            )
            for row in positions:
                connection.execute(
                    """
                    INSERT INTO position_valuations
                        (id, valuation_snapshot_id, position_id, price_quote_id,
                         market_value_trading, market_value_cad,
                         unrealized_gain_loss_trading, unrealized_gain_loss_cad,
                         portfolio_weight, data_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        valuation_id,
                        row["position_id"],
                        row.get("price_quote_id"),
                        row.get("market_value_trading"),
                        row.get("market_value_cad"),
                        row.get("unrealized_gain_loss_trading"),
                        row.get("unrealized_gain_loss_cad"),
                        row.get("portfolio_weight"),
                        row["data_status"],
                    ),
                )
        return valuation_id

    def latest_portfolio(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            valuation = connection.execute(
                """
                SELECT v.*, h.imported_at, h.source_as_of
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
                    pv.*, p.quantity, p.average_cost,
                    a.alias AS account_alias, a.account_type,
                    i.id AS instrument_id, i.canonical_symbol, i.security_name,
                    i.asset_type, i.exchange, i.trading_currency,
                    i.manual_sector, i.sector_source, i.sector_source_url,
                    i.sector_as_of,
                    q.price, q.currency AS price_currency, q.observed_at AS price_timestamp,
                    q.fetched_at AS price_fetched_at, q.source AS price_source,
                    q.source_url AS price_source_url, q.quote_status, q.delay_minutes,
                    q.stale AS price_stale
                FROM position_valuations pv
                JOIN positions p ON p.id = pv.position_id
                JOIN accounts a ON a.id = p.account_id
                JOIN instruments i ON i.id = p.instrument_id
                LEFT JOIN price_quotes q ON q.id = pv.price_quote_id
                WHERE pv.valuation_snapshot_id = ?
                ORDER BY CAST(pv.market_value_cad AS REAL) DESC, i.canonical_symbol
                """,
                (valuation["id"],),
            ).fetchall()
            fx = None
            if valuation["fx_rate_id"]:
                fx_row = connection.execute(
                    "SELECT * FROM fx_rates WHERE id = ?", (valuation["fx_rate_id"],)
                ).fetchone()
                fx = dict(fx_row) if fx_row else None
        return {
            "valuation_snapshot_id": valuation["id"],
            "holding_snapshot_id": valuation["holding_snapshot_id"],
            "created_at": valuation["created_at"],
            "imported_at": valuation["imported_at"],
            "source_as_of": valuation["source_as_of"],
            "total_cad": valuation["total_cad"],
            "priced_positions": valuation["priced_positions"],
            "total_positions": valuation["total_positions"],
            "position_coverage_pct": valuation["position_coverage_pct"],
            "warnings": json.loads(valuation["warnings_json"]),
            "fx": fx,
            "holdings": [dict(row) for row in rows],
        }

    def portfolio_history(self, limit: int = 180) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1_000))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, holding_snapshot_id, created_at, total_cad,
                       priced_positions, total_positions, position_coverage_pct
                FROM valuation_snapshots ORDER BY created_at DESC LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return list(reversed([dict(row) for row in rows]))

    def activities_view(
        self,
        *,
        activity_type: str | None = None,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        safe_types = {
            "BUY",
            "SELL",
            "DISTRIBUTION",
            "DEPOSIT",
            "WITHDRAWAL",
            "FEE",
            "INTEREST",
            "WITHHOLDING_TAX",
            "TRANSFER",
            "OTHER",
        }
        clauses: list[str] = []
        parameters: list[Any] = []
        if activity_type:
            normalized = activity_type.strip().upper()
            if normalized not in safe_types:
                raise ValueError("Unsupported activity filter")
            clauses.append("normalized_type = ?")
            parameters.append(normalized)
        if symbol:
            clauses.append("symbol LIKE ?")
            parameters.append(f"%{symbol.strip().upper()}%")
        if start_date:
            clauses.append("trade_date >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("trade_date <= ?")
            parameters.append(end_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 5_000))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT activity_key AS id, normalized_type, symbol, trade_date,
                       settlement_date, quantity, price, currency, fee, cash_amount,
                       source, source_as_of
                FROM brokerage_activities
                """
                + where
                + " ORDER BY trade_date DESC, activity_key LIMIT ?",
                (*parameters, safe_limit),
            ).fetchall()
            coverage_rows = connection.execute(
                """
                SELECT coverage_start, coverage_end, complete_initial_sync,
                       source_as_of, last_synced_at, warning
                FROM activity_coverage
                ORDER BY last_synced_at DESC
                """
            ).fetchall()
        coverage = {
            "start": min(
                (str(row["coverage_start"]) for row in coverage_rows if row["coverage_start"]),
                default=None,
            ),
            "end": max(
                (str(row["coverage_end"]) for row in coverage_rows if row["coverage_end"]),
                default=None,
            ),
            "complete": bool(coverage_rows)
            and all(bool(row["complete_initial_sync"]) for row in coverage_rows),
            "source_as_of": min(
                (str(row["source_as_of"]) for row in coverage_rows if row["source_as_of"]),
                default=None,
            ),
            "last_synced_at": max(
                (str(row["last_synced_at"]) for row in coverage_rows if row["last_synced_at"]),
                default=None,
            ),
        }
        warnings = [str(row["warning"]) for row in coverage_rows if row["warning"]]
        if not coverage_rows:
            warnings.append("No completed brokerage activity history has been synchronized.")
        else:
            warnings.append(
                "Coverage spans all pages returned by SnapTrade between the shown dates; "
                "account-lifetime brokerage coverage is not independently guaranteed."
            )
        return {
            "activities": [dict(row) for row in rows],
            "coverage": coverage,
            "warnings": list(dict.fromkeys(warnings)),
            "freshness": "daily_cached",
            "source": "SnapTrade daily completed activities",
        }
