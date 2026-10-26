"""History-oriented persistence for decisions, triggers, prompts, and AI reviews."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.database import Database
from app.repository import utc_now


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class JournalRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def profiles(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM investment_profiles ORDER BY symbol").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source_links"] = json.loads(item.pop("source_links_json"))
            result.append(item)
        return result

    def profile(self, instrument_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM investment_profiles WHERE instrument_id = ?", (instrument_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["source_links"] = json.loads(result.pop("source_links_json"))
        return result

    def save_profile(self, instrument_id: str, symbol: str, values: dict[str, Any]) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO investment_profiles
                    (instrument_id, symbol, portfolio_role, thesis_strength, why_owned,
                     supporting_evidence, principal_risks, invalidation_conditions,
                     maximum_weight, source_links_json, last_reviewed_date,
                     next_review_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    symbol = excluded.symbol,
                    portfolio_role = excluded.portfolio_role,
                    thesis_strength = excluded.thesis_strength,
                    why_owned = excluded.why_owned,
                    supporting_evidence = excluded.supporting_evidence,
                    principal_risks = excluded.principal_risks,
                    invalidation_conditions = excluded.invalidation_conditions,
                    maximum_weight = excluded.maximum_weight,
                    source_links_json = excluded.source_links_json,
                    last_reviewed_date = excluded.last_reviewed_date,
                    next_review_date = excluded.next_review_date,
                    updated_at = excluded.updated_at
                """,
                (
                    instrument_id,
                    symbol,
                    values.get("portfolio_role"),
                    values.get("thesis_strength"),
                    values.get("why_owned", ""),
                    values.get("supporting_evidence", ""),
                    values.get("principal_risks", ""),
                    values.get("invalidation_conditions", ""),
                    values.get("maximum_weight"),
                    _json(values.get("source_links", [])),
                    values.get("last_reviewed_date"),
                    values.get("next_review_date"),
                    now,
                ),
            )

    def decisions(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM current_decisions ORDER BY symbol").fetchall()
        return [dict(row) for row in rows]

    def save_decision(
        self,
        instrument_id: str,
        symbol: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = utc_now()
        history_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            prior = connection.execute(
                "SELECT decision FROM current_decisions WHERE instrument_id = ?",
                (instrument_id,),
            ).fetchone()
            previous = str(prior["decision"]) if prior else None
            connection.execute(
                """
                INSERT INTO decision_history
                    (id, instrument_id, symbol, decision_date, previous_decision,
                     new_decision, reason, claude_disposition, review_due_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    history_id,
                    instrument_id,
                    symbol,
                    values["decision_date"],
                    previous,
                    values["decision"],
                    values.get("reason", ""),
                    values.get("claude_disposition"),
                    values.get("review_due_date"),
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO current_decisions
                    (instrument_id, symbol, decision, reason, decision_date,
                     review_due_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    symbol = excluded.symbol,
                    decision = excluded.decision,
                    reason = excluded.reason,
                    decision_date = excluded.decision_date,
                    review_due_date = excluded.review_due_date,
                    updated_at = excluded.updated_at
                """,
                (
                    instrument_id,
                    symbol,
                    values["decision"],
                    values.get("reason", ""),
                    values["decision_date"],
                    values.get("review_due_date"),
                    created_at,
                ),
            )
        return {"id": history_id, "previous_decision": previous, "created_at": created_at}

    def decision_history(self, instrument_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM decision_history"
        parameters: tuple[Any, ...] = ()
        if instrument_id:
            query += " WHERE instrument_id = ?"
            parameters = (instrument_id,)
        query += " ORDER BY decision_date DESC, created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def triggers(self, instrument_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_triggers"
        parameters: tuple[Any, ...] = ()
        if instrument_id:
            query += " WHERE instrument_id = ?"
            parameters = (instrument_id,)
        query += (
            " ORDER BY CASE state WHEN 'TRIGGERED' THEN 0 "
            "WHEN 'ACTIVE' THEN 1 ELSE 2 END, created_at DESC"
        )
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def create_trigger(
        self, instrument_id: str, symbol: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        trigger_id = uuid.uuid4().hex
        created_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO review_triggers
                    (id, instrument_id, symbol, trigger_type, lower_value, upper_value,
                     trigger_date, note, reason, expires_at, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                """,
                (
                    trigger_id,
                    instrument_id,
                    symbol,
                    values["trigger_type"],
                    values.get("lower_value"),
                    values.get("upper_value"),
                    values.get("trigger_date"),
                    values.get("note", ""),
                    values.get("reason", ""),
                    values.get("expires_at"),
                    created_at,
                ),
            )
        return {"id": trigger_id, "created_at": created_at}

    def expire_trigger(self, trigger_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE review_triggers SET state = 'EXPIRED' WHERE id = ? AND state = 'ACTIVE'",
                (trigger_id,),
            )

    def trigger(self, trigger_id: str, evidence: dict[str, Any]) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT symbol, state FROM review_triggers WHERE id = ?", (trigger_id,)
            ).fetchone()
            if row is None or row["state"] != "ACTIVE":
                return
            connection.execute(
                """
                UPDATE review_triggers
                SET state = 'TRIGGERED', triggered_at = ?, observed_value = ?,
                    quote_source = ?, quote_timestamp = ?, frozen_holding_snapshot_id = ?,
                    frozen_valuation_snapshot_id = ?
                WHERE id = ? AND state = 'ACTIVE'
                """,
                (
                    now,
                    evidence.get("observed_value"),
                    evidence.get("quote_source"),
                    evidence.get("quote_timestamp"),
                    evidence.get("holding_snapshot_id"),
                    evidence.get("valuation_snapshot_id"),
                    trigger_id,
                ),
            )
            connection.execute(
                "INSERT INTO local_alerts (id, trigger_id, created_at, message) VALUES (?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    trigger_id,
                    now,
                    f"{row['symbol']} review trigger is due. Review only; no order was created.",
                ),
            )

    def alerts(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.trigger_id, a.created_at, a.message,
                       t.symbol, t.trigger_type, t.state
                FROM local_alerts a
                JOIN review_triggers t ON t.id = a.trigger_id
                WHERE a.dismissed_at IS NULL
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def prompts(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM claude_prompts ORDER BY is_default DESC, name"
            ).fetchall()
        return [dict(row) for row in rows]

    def save_prompt(self, prompt_id: str | None, name: str, prompt_text: str) -> dict[str, Any]:
        now = utc_now()
        target_id = prompt_id or uuid.uuid4().hex
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM claude_prompts WHERE id = ?", (target_id,)
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE claude_prompts SET name = ?, prompt_text = ?, updated_at = ? WHERE id = ?",
                    (name, prompt_text, now, target_id),
                )
            else:
                is_default = int(
                    connection.execute("SELECT COUNT(*) AS count FROM claude_prompts").fetchone()[
                        "count"
                    ]
                    == 0
                )
                connection.execute(
                    """
                    INSERT INTO claude_prompts
                        (id, name, prompt_text, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (target_id, name, prompt_text, is_default, now, now),
                )
        return next(item for item in self.prompts() if item["id"] == target_id)

    def prompt(self, prompt_id: str) -> dict[str, Any] | None:
        return next((row for row in self.prompts() if row["id"] == prompt_id), None)

    def save_review_export(self, values: dict[str, Any]) -> str:
        export_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO claude_review_exports
                    (id, instrument_id, symbol, trigger_id, prompt_id, privacy_json,
                     markdown_text, holdings_as_of, evidence_as_of, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    values["instrument_id"],
                    values["symbol"],
                    values.get("trigger_id"),
                    values["prompt_id"],
                    _json(values["privacy"]),
                    values["markdown"],
                    values.get("holdings_as_of"),
                    values.get("evidence_as_of"),
                    values["generated_at"],
                ),
            )
        return export_id

    def save_ai_review(self, instrument_id: str, symbol: str, values: dict[str, Any]) -> str:
        review_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO ai_reviews
                    (id, instrument_id, symbol, review_date, evidence_as_of, suggestion,
                     explanation, bull_case, bear_case, principal_risks,
                     missing_information, change_conditions, source_links_json,
                     claude_model, disposition, original_markdown, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    instrument_id,
                    symbol,
                    values["review_date"],
                    values.get("evidence_as_of"),
                    values["suggestion"],
                    values.get("explanation", ""),
                    values.get("bull_case", ""),
                    values.get("bear_case", ""),
                    values.get("principal_risks", ""),
                    values.get("missing_information", ""),
                    values.get("change_conditions", ""),
                    _json(values.get("source_links", [])),
                    values.get("claude_model"),
                    values["disposition"],
                    values["original_markdown"],
                    utc_now(),
                ),
            )
        return review_id

    def ai_reviews(self, instrument_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM ai_reviews"
        parameters: tuple[Any, ...] = ()
        if instrument_id:
            query += " WHERE instrument_id = ?"
            parameters = (instrument_id,)
        query += " ORDER BY review_date DESC, created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source_links"] = json.loads(item.pop("source_links_json"))
            result.append(item)
        return result
