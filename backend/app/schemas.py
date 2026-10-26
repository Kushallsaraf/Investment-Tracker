"""Public API schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ImportIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    row_number: int | None = None
    field: str | None = None


class ImportRow(BaseModel):
    row_number: int
    raw_symbol: str
    canonical_symbol: str | None = None
    security_name: str
    provided_exchange: str
    exchange: str | None = None
    provided_asset_type: str
    asset_type: Literal["STOCK", "ETF", "CASH"] | None = None
    trading_currency: str
    quantity: str | None
    average_cost: str | None
    imported_price: str | None
    imported_market_value: str | None
    account_alias: str
    account_type: str
    resolution_status: str
    issues: list[ImportIssue]


class ImportPreview(BaseModel):
    draft_id: str
    created_at: str
    expires_at: str
    source_as_of: str | None
    rows: list[ImportRow]
    issues: list[ImportIssue]
    ignored_columns: list[str]
    error_count: int
    warning_count: int
    can_confirm: bool


class RowOverride(BaseModel):
    row_number: int = Field(ge=2)
    symbol: str | None = Field(default=None, max_length=40)
    exchange: Literal["TSX", "TSXV", "US", "CASH"] | None = None
    asset_type: Literal["STOCK", "ETF", "CASH"] | None = None
    currency: Literal["CAD", "USD"] | None = None


class RevalidateRequest(BaseModel):
    overrides: list[RowOverride] = Field(default_factory=list, max_length=5_000)


class ConfirmImportRequest(BaseModel):
    accept_warnings: bool = False


class ConfirmImportResponse(BaseModel):
    status: Literal["ok"] = "ok"
    holding_snapshot_id: str
    valuation_snapshot_id: str


class RefreshResponse(BaseModel):
    status: Literal["ok"] = "ok"
    valuation_snapshot_id: str


SectorName = Literal[
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
    "Other",
]


class SectorUpdateRequest(BaseModel):
    sector: SectorName | None = None


class ApplySnapTradeSyncRequest(BaseModel):
    confirm: Literal["APPLY"]


class DisconnectSnapTradeRequest(BaseModel):
    confirm: Literal["DISCONNECT"]


class DeleteLocalBrokerageDataRequest(BaseModel):
    confirm: Literal["DELETE LOCAL DATA"]


DecisionName = Literal[
    "WATCH", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "EXIT_CANDIDATE"
]
ClaudeSuggestion = Literal[
    "CONSIDER_BUY", "HOLD", "CONSIDER_REDUCE", "CONSIDER_EXIT", "INSUFFICIENT_DATA"
]
SuggestionDisposition = Literal["ACCEPTED", "REJECTED", "CONSIDERING"]


class InvestmentProfileUpdate(BaseModel):
    portfolio_role: Literal["CORE", "DIVERSIFIER", "INCOME", "SPECULATIVE"] | None = None
    thesis_strength: int | None = Field(default=None, ge=1, le=5)
    why_owned: str = Field(default="", max_length=20_000)
    supporting_evidence: str = Field(default="", max_length=20_000)
    principal_risks: str = Field(default="", max_length=20_000)
    invalidation_conditions: str = Field(default="", max_length=20_000)
    maximum_weight: str | None = Field(default=None, max_length=32)
    source_links: list[str] = Field(default_factory=list, max_length=100)
    last_reviewed_date: date | None = None
    next_review_date: date | None = None


class DecisionUpdate(BaseModel):
    decision: DecisionName
    decision_date: date
    reason: str = Field(default="", max_length=20_000)
    claude_disposition: SuggestionDisposition | None = None
    review_due_date: date | None = None


class TriggerCreate(BaseModel):
    trigger_type: Literal[
        "PRICE_BELOW",
        "PRICE_ABOVE",
        "CONSIDER_ADD_RANGE",
        "CONSIDER_REDUCE_RANGE",
        "DATE",
        "AFTER_EARNINGS",
        "THESIS_NOTE",
    ]
    lower_value: str | None = Field(default=None, max_length=32)
    upper_value: str | None = Field(default=None, max_length=32)
    trigger_date: date | None = None
    note: str = Field(default="", max_length=10_000)
    reason: str = Field(default="", max_length=10_000)
    expires_at: date | None = None


class ClaudePromptUpsert(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    prompt_text: str = Field(min_length=1, max_length=100_000)


class ReviewPackPrivacy(BaseModel):
    weights_only: bool = True
    include_quantities: bool = False
    include_dollar_values: bool = False
    include_account_type: bool = False


class ReviewPackRequest(BaseModel):
    instrument_id: str = Field(min_length=1, max_length=64)
    prompt_id: str = Field(min_length=1, max_length=64)
    trigger_id: str | None = Field(default=None, max_length=64)
    privacy: ReviewPackPrivacy = Field(default_factory=ReviewPackPrivacy)


class AIReviewCreate(BaseModel):
    instrument_id: str = Field(min_length=1, max_length=64)
    review_date: date
    evidence_as_of: date | None = None
    suggestion: ClaudeSuggestion
    explanation: str = Field(default="", max_length=50_000)
    bull_case: str = Field(default="", max_length=30_000)
    bear_case: str = Field(default="", max_length=30_000)
    principal_risks: str = Field(default="", max_length=30_000)
    missing_information: str = Field(default="", max_length=30_000)
    change_conditions: str = Field(default="", max_length=30_000)
    source_links: list[str] = Field(default_factory=list, max_length=200)
    claude_model: str | None = Field(default=None, max_length=120)
    disposition: SuggestionDisposition = "CONSIDERING"
    original_markdown: str = Field(min_length=1, max_length=250_000)
