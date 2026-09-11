"""Public API schemas."""

from __future__ import annotations

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
