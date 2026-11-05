"""History-oriented persistence for decisions, triggers, prompts, and AI reviews."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from app.database import Database
from app.repository import utc_now


def _alert_message(trigger: dict[str, Any], observed: str | None) -> str:
    symbol = trigger["symbol"]
    if not trigger.get("exit_plan_id"):
        return f"{symbol} review trigger is due. Review only; no order was created."
    close = f"closed at {Decimal(observed).quantize(Decimal('0.01'))}" if observed else "reached its level"
    if trigger["trigger_type"] == "PRICE_ABOVE":
        event = f"{symbol} {close}, at or above the exit-plan target of {trigger['upper_value']}."
    elif trigger["trigger_type"] == "PRICE_BELOW":
        event = f"{symbol} {close}, at or below the exit-plan stop of {trigger['lower_value']}."
    else:
        event = f"{symbol} exit-plan review date has arrived."
    return f"{event} Review only; no order was created."


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
                     trigger_date, note, reason, expires_at, state, created_at, exit_plan_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
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
                    values.get("exit_plan_id"),
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
                """
                SELECT t.symbol, t.state, t.trigger_type, t.lower_value, t.upper_value,
                       t.exit_plan_id
                FROM review_triggers t WHERE t.id = ?
                """,
                (trigger_id,),
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
                    _alert_message(dict(row), evidence.get("observed_value")),
                ),
            )

    def alerts(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.trigger_id, a.created_at, a.message, a.notified_at,
                       t.symbol, t.trigger_type, t.state, t.exit_plan_id,
                       p.reasoning AS exit_plan_reasoning
                FROM local_alerts a
                JOIN review_triggers t ON t.id = a.trigger_id
                LEFT JOIN exit_plans p ON p.id = t.exit_plan_id
                WHERE a.dismissed_at IS NULL
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_alert_notified(self, alert_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE local_alerts SET notified_at = ? WHERE id = ? AND notified_at IS NULL",
                (utc_now(), alert_id),
            )

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

    def notes(self, symbol: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notes WHERE symbol = ? ORDER BY created_at DESC", (symbol,)
            ).fetchall()
        return [dict(row) for row in rows]

    def note(self, note_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row else None

    def add_note(self, symbol: str, body: str, pinned_date: str | None, author: str) -> dict[str, Any]:
        note_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO notes (id, symbol, body, pinned_date, author, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (note_id, symbol, body, pinned_date, author, now, now),
            )
        return self.note(note_id) or {}

    def update_note(self, note_id: str, body: str, pinned_date: str | None) -> dict[str, Any]:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE notes SET body = ?, pinned_date = ?, updated_at = ? WHERE id = ?",
                (body, pinned_date, utc_now(), note_id),
            ).rowcount
        if not updated:
            raise KeyError("Note was not found")
        return self.note(note_id) or {}

    def delete_note(self, note_id: str) -> None:
        with self.database.transaction() as connection:
            deleted = connection.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount
        if not deleted:
            raise KeyError("Note was not found")

    def exit_plans(self, symbol: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        query = "SELECT * FROM exit_plans"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [dict(row) for row in rows]

    def exit_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM exit_plans WHERE id = ?", (plan_id,)).fetchone()
        return dict(row) if row else None

    def add_exit_plan(self, values: dict[str, Any]) -> dict[str, Any]:
        """Store a new proposal and retire the same author's older open proposals for that ticker."""
        plan_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE exit_plans SET status = 'SUPERSEDED', decided_at = ?
                WHERE symbol = ? AND proposed_by = ? AND status = 'PROPOSED'
                """,
                (now, values["symbol"], values["proposed_by"]),
            )
            connection.execute(
                """
                INSERT INTO exit_plans
                    (id, symbol, target_price, stop_price, review_date, reasoning, proposed_by,
                     status, reference_price, reference_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?, ?, ?)
                """,
                (
                    plan_id,
                    values["symbol"],
                    values.get("target_price"),
                    values.get("stop_price"),
                    values.get("review_date"),
                    values["reasoning"],
                    values["proposed_by"],
                    values.get("reference_price"),
                    values.get("reference_date"),
                    now,
                ),
            )
        return self.exit_plan(plan_id) or {}

    def decide_exit_plan(self, plan_id: str, status: str, note_id: str | None = None) -> dict[str, Any]:
        """Accept or reject an open proposal. Accepting retires the ticker's earlier accepted plan."""
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT symbol, status FROM exit_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Exit plan was not found")
            if row["status"] != "PROPOSED":
                raise ValueError(f"This exit plan is already {str(row['status']).lower()}")
            if status == "ACCEPTED":
                previous = [
                    item["id"]
                    for item in connection.execute(
                        "SELECT id FROM exit_plans WHERE symbol = ? AND status = 'ACCEPTED'",
                        (row["symbol"],),
                    ).fetchall()
                ]
                for previous_id in previous:
                    connection.execute(
                        "UPDATE exit_plans SET status = 'SUPERSEDED', decided_at = ? WHERE id = ?",
                        (now, previous_id),
                    )
                    connection.execute(
                        """
                        UPDATE review_triggers SET state = 'DISMISSED'
                        WHERE exit_plan_id = ? AND state IN ('ACTIVE', 'TRIGGERED')
                        """,
                        (previous_id,),
                    )
            connection.execute(
                "UPDATE exit_plans SET status = ?, decided_at = ?, note_id = ? WHERE id = ?",
                (status, now, note_id, plan_id),
            )
        return self.exit_plan(plan_id) or {}
