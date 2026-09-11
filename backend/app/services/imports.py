"""Two-step import preview, correction, and confirmation workflow."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.config import settings
from app.importers.wealthsimple import (
    apply_overrides,
    load_or_create_secret,
    parse_holdings_csv,
)
from app.repository import PortfolioRepository


class ImportService:
    def __init__(self, repository: PortfolioRepository | None = None) -> None:
        self.repository = repository or PortfolioRepository()

    def preview(self, path: Path) -> dict[str, Any]:
        content = path.read_bytes()
        source_hash = hashlib.sha256(content).hexdigest()
        secret = load_or_create_secret(settings.secret_path)
        result = parse_holdings_csv(content, secret=secret)
        issues = list(result.issues)
        if self.repository.has_import_hash(source_hash):
            issues.append(
                {
                    "severity": "warning",
                    "code": "DUPLICATE_IMPORT_FILE",
                    "message": "This exact holdings file was imported before.",
                    "row_number": None,
                    "field": None,
                }
            )
        draft = self.repository.create_draft(
            source_hash=source_hash,
            rows=result.rows,
            source_as_of=result.source_as_of,
            issues=issues,
            ignored_columns=result.ignored_columns,
        )
        return self.public_preview(draft)

    def revalidate(self, draft_id: str, overrides: list[dict[str, Any]]) -> dict[str, Any]:
        draft = self.repository.get_draft(draft_id)
        rows, row_issues = apply_overrides(draft["rows"], overrides)
        global_issues = [issue for issue in draft["issues"] if issue.get("row_number") is None]
        updated = self.repository.update_draft(
            draft_id,
            rows=rows,
            issues=[*global_issues, *row_issues],
        )
        return self.public_preview(updated)

    def confirm(self, draft_id: str, *, accept_warnings: bool) -> str:
        draft = self.repository.get_draft(draft_id)
        if any(issue["severity"] == "error" for issue in draft["issues"]):
            raise ValueError("Resolve every import error before confirming")
        if not accept_warnings and any(issue["severity"] == "warning" for issue in draft["issues"]):
            raise ValueError("Review the warnings and explicitly accept them before confirming")
        return self.repository.persist_draft(draft_id)

    @staticmethod
    def public_preview(draft: dict[str, Any]) -> dict[str, Any]:
        issues = draft["issues"]
        safe_rows = []
        for row in draft["rows"]:
            safe_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"account_fingerprint", "parse_issues", "book_value"}
                }
            )
        error_count = sum(issue["severity"] == "error" for issue in issues)
        warning_count = sum(issue["severity"] == "warning" for issue in issues)
        return {
            "draft_id": draft["id"],
            "created_at": draft["created_at"],
            "expires_at": draft["expires_at"],
            "source_as_of": draft["source_as_of"],
            "rows": safe_rows,
            "issues": issues,
            "ignored_columns": draft["ignored_columns"],
            "error_count": error_count,
            "warning_count": warning_count,
            "can_confirm": error_count == 0,
        }
