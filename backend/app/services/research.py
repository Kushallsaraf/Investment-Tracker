"""Manual Claude review-pack generation and separate AI-response storage."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.journal_repository import JournalRepository
from app.repository import PortfolioRepository
from app.services.journal import CLAUDE_SUGGESTIONS, DISPOSITIONS
from app.services.sectors import SectorService

DEFAULT_PROMPT_NAME = "Beginner US investment review"
DEFAULT_PROMPT = """Act as a careful research assistant for a beginner US retail investor.
Assess the evidence without placing a trade or predicting future returns. Separate verified facts,
interpretation, and missing information. Cite primary sources with exact as-of dates. Prefer SEC
filings (10-K, 10-Q, 8-K) for companies and current prospectuses and issuer-published holdings for
ETFs. Use adjusted total-return data including dividends for performance comparisons. Explain the
bull case, bear case, material risks, what evidence is missing, and which conditions would change
the conclusion. End with a non-binding suggestion from the allowed choices and a short human-review
checklist. This is research, not financial advice."""


def _display(value: Any) -> str:
    return str(value) if value not in (None, "") else "NOT AVAILABLE"


class ResearchService:
    def __init__(
        self,
        repository: JournalRepository,
        portfolio_repository: PortfolioRepository,
        sector_service: SectorService,
    ) -> None:
        self.repository = repository
        self.portfolio_repository = portfolio_repository
        self.sector_service = sector_service

    def prompts(self) -> list[dict[str, Any]]:
        prompts = self.repository.prompts()
        if not prompts:
            self.repository.save_prompt(None, DEFAULT_PROMPT_NAME, DEFAULT_PROMPT)
            prompts = self.repository.prompts()
        return prompts

    def save_prompt(self, prompt_id: str | None, name: str, prompt_text: str) -> dict[str, Any]:
        if not name.strip() or not prompt_text.strip():
            raise ValueError("Prompt name and prompt text are required")
        return self.repository.save_prompt(prompt_id, name.strip(), prompt_text.strip())

    def _holding(self, instrument_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        portfolio = self.portfolio_repository.latest_portfolio()
        holding = next(
            (
                row
                for row in (portfolio or {}).get("holdings", [])
                if row["instrument_id"] == instrument_id
            ),
            None,
        )
        if portfolio is None or holding is None:
            raise KeyError("Holding was not found in the current portfolio snapshot")
        return portfolio, holding

    def generate_pack(
        self,
        *,
        instrument_id: str,
        prompt_id: str,
        trigger_id: str | None,
        privacy: dict[str, bool],
        save: bool,
    ) -> dict[str, Any]:
        portfolio, holding = self._holding(instrument_id)
        prompt = self.repository.prompt(prompt_id)
        if prompt is None:
            raise KeyError("Reusable Claude prompt was not found")
        profile = self.repository.profile(instrument_id) or {}
        decision = next(
            (
                row
                for row in self.repository.decisions()
                if row["instrument_id"] == instrument_id
            ),
            None,
        )
        trigger = next(
            (row for row in self.repository.triggers(instrument_id) if row["id"] == trigger_id),
            None,
        ) if trigger_id else None
        sectors = self.sector_service.latest()
        etf_evidence = next(
            (
                row
                for row in (sectors or {}).get("evidence", [])
                if row["symbol"] == holding["canonical_symbol"]
            ),
            None,
        )
        weights_only = bool(privacy.get("weights_only", True))
        include_quantities = bool(privacy.get("include_quantities", False)) and not weights_only
        include_dollars = bool(privacy.get("include_dollar_values", False)) and not weights_only
        include_account = bool(privacy.get("include_account_name", False))
        effective_privacy = {
            "weights_only": weights_only,
            "include_quantities": include_quantities,
            "include_dollar_values": include_dollars,
            "include_account_name": include_account,
        }
        generated_at = datetime.now(UTC).isoformat()
        missing = [
            "Adjusted total-return performance is not available from a verified provider.",
            "Historical risk is unavailable until reliable adjusted total-return observations exist.",
        ]
        if not profile:
            missing.append("No local conviction/thesis profile has been recorded.")
        if holding.get("price") is None:
            missing.append("Latest independent market price is missing.")
        if holding["asset_type"] == "ETF" and etf_evidence is None:
            missing.append("No supported issuer ETF evidence profile is available.")
        missing.extend(portfolio.get("warnings") or [])
        lines = [
            f"# Manual review request: {holding['canonical_symbol']}",
            "",
            f"Generated: {generated_at}",
            f"Holdings snapshot as of: {_display(portfolio.get('snapshot_created_at'))}",
            "Workflow: Manual copy/export to Claude; no Claude API is connected.",
            "Guardrail: Research only. No order or brokerage action is authorized.",
            "",
            "## Holding identity",
            f"- Symbol: {holding['canonical_symbol']}",
            f"- Name: {holding['security_name']}",
            f"- Type: {holding['asset_type']}",
            f"- Exchange: {holding['exchange']}",
            f"- Portfolio weight: {_display(holding.get('portfolio_weight'))}",
        ]
        if include_account:
            lines.append(f"- Account: {holding['account_name']}")
        if include_quantities:
            lines.append(f"- Quantity: {_display(holding.get('quantity'))}")
        if include_dollars:
            lines.extend(
                [
                    f"- Average cost: {_display(holding.get('average_cost'))} USD",
                    f"- Market value: {_display(holding.get('market_value'))} USD",
                    f"- Unrealized gain/loss: {_display(holding.get('unrealized_gain_loss'))} USD",
                ]
            )
        lines.extend(
            [
                "",
                "## My decision and conviction",
                f"- My decision: {_display((decision or {}).get('decision'))}",
                f"- Decision date: {_display((decision or {}).get('decision_date'))}",
                f"- Portfolio role: {_display(profile.get('portfolio_role'))}",
                f"- Thesis strength: {_display(profile.get('thesis_strength'))}",
                f"- Why I own it: {_display(profile.get('why_owned'))}",
                f"- Supporting evidence: {_display(profile.get('supporting_evidence'))}",
                f"- Principal risks: {_display(profile.get('principal_risks'))}",
                f"- Thesis invalidation: {_display(profile.get('invalidation_conditions'))}",
                f"- Maximum weight: {_display(profile.get('maximum_weight'))}",
                "",
                "## Review trigger",
                f"- Type: {_display((trigger or {}).get('trigger_type'))}",
                f"- Reason: {_display((trigger or {}).get('reason'))}",
                f"- Triggered at: {_display((trigger or {}).get('triggered_at'))}",
                f"- Observed value: {_display((trigger or {}).get('observed_value'))}",
                "",
                "## Latest independent price evidence",
                f"- Price: {_display(holding.get('price'))} USD",
                f"- Status: {_display(holding.get('quote_status'))}",
                f"- Price timestamp: {_display(holding.get('price_timestamp'))}",
                f"- Fetch timestamp: {_display(holding.get('price_fetched_at'))}",
                f"- Source: {_display(holding.get('price_source'))}",
                f"- Source URL: {_display(holding.get('price_source_url'))}",
                "",
                "## ETF/company evidence",
            ]
        )
        if etf_evidence:
            lines.extend(
                [
                    f"- Issuer: {_display(etf_evidence.get('issuer'))}",
                    f"- Evidence as of: {_display(etf_evidence.get('as_of'))}",
                    f"- Verified on: {_display(etf_evidence.get('verified_on'))}",
                    f"- Coverage: {_display(etf_evidence.get('coverage_pct'))}",
                    f"- Method: {_display(etf_evidence.get('method'))}",
                    f"- Source URL: {_display(etf_evidence.get('source_url'))}",
                ]
            )
        else:
            lines.append("- NOT AVAILABLE: no locally verified profile is available.")
        lines.extend(["", "## Missing, stale, or conflicting data"])
        lines.extend(f"- {item}" for item in dict.fromkeys(missing))
        source_links = profile.get("source_links") or []
        lines.extend(["", "## My source links"])
        lines.extend(f"- {link}" for link in source_links)
        if not source_links:
            lines.append("- NOT AVAILABLE")
        lines.extend(
            [
                "",
                "## Reusable Claude prompt",
                str(prompt["prompt_text"]),
                "",
                "---",
                "AI output is research for human review, not financial advice or a "
                "prediction of future returns.",
            ]
        )
        markdown = "\n".join(lines)
        export_id = None
        values = {
            "instrument_id": instrument_id,
            "symbol": holding["canonical_symbol"],
            "trigger_id": trigger_id,
            "prompt_id": prompt_id,
            "privacy": effective_privacy,
            "markdown": markdown,
            "holdings_as_of": portfolio.get("snapshot_created_at"),
            "evidence_as_of": (etf_evidence or {}).get("as_of"),
            "generated_at": generated_at,
        }
        if save:
            export_id = self.repository.save_review_export(values)
        return {"export_id": export_id, **values}

    def save_ai_review(
        self, instrument_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        _, holding = self._holding(instrument_id)
        if values.get("suggestion") not in CLAUDE_SUGGESTIONS:
            raise ValueError("Unsupported Claude suggestion")
        if values.get("disposition") not in DISPOSITIONS:
            raise ValueError("Unsupported AI-review status")
        review_date = values.get("review_date")
        try:
            date.fromisoformat(str(review_date))
        except ValueError as exc:
            raise ValueError("Review date must be an ISO date") from exc
        review_id = self.repository.save_ai_review(
            instrument_id, str(holding["canonical_symbol"]), values
        )
        return {"id": review_id}

    def reviews(self) -> list[dict[str, Any]]:
        return self.repository.ai_reviews()
