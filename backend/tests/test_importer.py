from __future__ import annotations

from app.importers.wealthsimple import apply_overrides, parse_holdings_csv

SECRET = b"synthetic-test-secret-that-is-not-private"


def test_valid_holdings_are_normalized_without_plaintext_account_number() -> None:
    content = b"""Account Type,Account Number,Symbol,Security Name,Security Type,Exchange,Currency,\
Quantity,Average Cost,Address
TFSA,WS-TEST-001,XIC,iShares Core ETF,ETF,TSX,CAD,12.5,31.20,123 Synthetic Street
RRSP,WS-TEST-002,AAPL,Apple Inc,Stock,NASDAQ,USD,2,180.00,456 Example Road
"""
    result = parse_holdings_csv(content, secret=SECRET)

    assert [row["canonical_symbol"] for row in result.rows] == ["XIC.TO", "AAPL"]
    assert [row["asset_type"] for row in result.rows] == ["ETF", "STOCK"]
    assert result.rows[0]["account_alias"].startswith("TFSA-")
    assert "WS-TEST-001" not in repr(result.rows)
    assert "123 Synthetic Street" not in repr(result.rows)
    assert any(issue["code"] == "PII_COLUMNS_IGNORED" for issue in result.issues)


def test_bare_symbol_without_exchange_requires_review() -> None:
    content = b"""Account Type,Symbol,Security Name,Security Type,Currency,Quantity
TFSA,XIC,iShares Core ETF,ETF,CAD,10
"""
    result = parse_holdings_csv(content, secret=SECRET)

    assert result.rows[0]["canonical_symbol"] is None
    assert any(issue["code"] == "AMBIGUOUS_EXCHANGE" for issue in result.issues)

    rows, issues = apply_overrides(
        result.rows,
        [{"row_number": 2, "exchange": "TSX", "asset_type": "ETF", "currency": "CAD"}],
    )
    assert rows[0]["canonical_symbol"] == "XIC.TO"
    assert not any(issue["severity"] == "error" for issue in issues)


def test_duplicate_holding_in_same_account_is_blocked() -> None:
    content = b"""Account Type,Symbol,Security Type,Exchange,Currency,Quantity
TFSA,XIC,ETF,TSX,CAD,10
TFSA,XIC,ETF,TSX,CAD,2
"""
    result = parse_holdings_csv(content, secret=SECRET)
    assert any(issue["code"] == "DUPLICATE_HOLDING" for issue in result.issues)


def test_malformed_quantity_is_blocked() -> None:
    content = b"""Account Type,Symbol,Security Type,Exchange,Currency,Quantity
TFSA,XIC,ETF,TSX,CAD,not-a-number
"""
    result = parse_holdings_csv(content, secret=SECRET)
    assert any(issue["code"] == "MALFORMED_QUANTITY" for issue in result.issues)


def test_average_cost_can_be_derived_with_visible_warning() -> None:
    content = b"""Account Type,Symbol,Security Type,Exchange,Currency,Quantity,Book Value
TFSA,XIC,ETF,TSX,CAD,4,120.00
"""
    result = parse_holdings_csv(content, secret=SECRET)
    assert result.rows[0]["average_cost"] == "30.00"
    assert any(issue["code"] == "AVERAGE_COST_DERIVED" for issue in result.issues)


def test_current_wealthsimple_export_columns_and_cash_are_supported() -> None:
    content = b"""Account Name,Account Type,Account Number,Symbol,Exchange,MIC,Name,Security Type,\
Quantity,Market Price,Market Price Currency,Book Value (Market),Book Value Currency (Market),\
Market Value,Market Value Currency
Synthetic TFSA,TFSA,WS-SYNTHETIC-001,XIC,TSX,XTSE,Synthetic ETF,\
EXCHANGE_TRADED_FUND,4,40,CAD,120,CAD,160,CAD
Synthetic TFSA,TFSA,WS-SYNTHETIC-001,CAD,,,Canadian Dollar,CURRENCY,100,1,CAD,100,CAD,100,CAD
Synthetic TFSA,,,,,,,,,,,,,
"""
    result = parse_holdings_csv(content, secret=SECRET)

    assert len(result.rows) == 2
    assert [row["canonical_symbol"] for row in result.rows] == ["XIC.TO", "CASH-CAD"]
    assert [row["asset_type"] for row in result.rows] == ["ETF", "CASH"]
    assert result.rows[0]["average_cost"] == "30"
    assert all(row["trading_currency"] == "CAD" for row in result.rows)
    assert any(issue["code"] == "NON_HOLDING_ROWS_SKIPPED" for issue in result.issues)
    assert not any(issue["severity"] == "error" for issue in result.issues)


def test_parse_error_marks_row_as_needing_review() -> None:
    content = b"""Account Type,Symbol,Security Type,Exchange,Currency,Quantity
TFSA,XIC,ETF,TSX,CAD,not-a-number
"""
    result = parse_holdings_csv(content, secret=SECRET)

    assert result.rows[0]["resolution_status"] == "needs_review"
