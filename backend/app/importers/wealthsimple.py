"""Strict, privacy-preserving Wealthsimple holdings-report CSV importer."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

MAX_IMPORT_ROWS = 5_000


def _header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "account": (
        "account",
        "account name",
        "account description",
        "account label",
    ),
    "account_number": ("account number", "account id", "account no", "account #"),
    "account_type": ("account type", "registered account type", "registration type"),
    "symbol": ("symbol", "ticker", "ticker symbol", "security symbol"),
    "security_name": ("security name", "name", "description", "instrument name"),
    "asset_type": ("security type", "asset type", "instrument type", "type"),
    "exchange": ("exchange", "market", "listing exchange", "mic"),
    "currency": (
        "currency",
        "currency code",
        "price currency",
        "market price currency",
        "market value currency",
    ),
    "quantity": ("quantity", "shares", "units", "position quantity"),
    "average_cost": (
        "average cost",
        "avg cost",
        "average price",
        "book cost per share",
        "cost basis per unit",
    ),
    "book_value": (
        "book value market",
        "book value",
        "cost basis",
        "total cost",
        "book cost",
        "book value cad",
    ),
    "price": ("market price", "current price", "last price", "price"),
    "market_value": ("market value", "position value", "current value"),
    "as_of": ("as of", "as of date", "effective date", "statement date"),
}

PII_HEADERS = {
    "first name",
    "last name",
    "full name",
    "client name",
    "address",
    "street address",
    "email",
    "email address",
    "phone",
    "phone number",
    "sin",
    "social insurance number",
}

EXCHANGE_ALIASES = {
    "TSX": "TSX",
    "TORONTO STOCK EXCHANGE": "TSX",
    "TSE": "TSX",
    "TSXV": "TSXV",
    "TSX VENTURE": "TSXV",
    "TSX VENTURE EXCHANGE": "TSXV",
    "CVE": "TSXV",
    "NASDAQ": "US",
    "NASDAQGS": "US",
    "NASDAQ GLOBAL SELECT": "US",
    "NYSE": "US",
    "NYSE ARCA": "US",
    "NYSEAMERICAN": "US",
    "AMEX": "US",
    "US": "US",
    "USA": "US",
    "CASH": "CASH",
}

ACCOUNT_TYPES = (
    "TFSA",
    "RRSP",
    "FHSA",
    "RESP",
    "LIRA",
    "RRIF",
    "NON_REGISTERED",
    "MARGIN",
    "CASH",
    "CRYPTO",
    "MANAGED",
)


@dataclass(frozen=True)
class ImportResult:
    rows: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    ignored_columns: list[str]
    source_as_of: str | None


def load_or_create_secret(path: Path) -> bytes:
    """Return a private local HMAC secret used to alias account identifiers."""
    if path.exists():
        return path.read_bytes()
    secret = os.urandom(32)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, secret)
    finally:
        os.close(descriptor)
    return secret


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The CSV must use UTF-8 or UTF-16 encoding")


def _parse_decimal(value: Any, *, required: bool = False) -> Decimal | None:
    raw = "" if value is None else str(value).strip()
    if not raw:
        if required:
            raise ValueError("value is required")
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"(?i)\b(?:CAD|USD)\b", "", raw)
    cleaned = cleaned.replace("$", "").replace(",", "").replace("%", "").strip("() ")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid number: {raw}") from exc
    if not parsed.is_finite():
        raise ValueError(f"invalid number: {raw}")
    return -parsed if negative else parsed


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _account_type(*values: Any) -> str:
    joined = " ".join(str(value or "") for value in values).upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", joined)
    if "NON REGISTERED" in normalized or "PERSONAL" in normalized:
        return "NON_REGISTERED"
    for account_type in ACCOUNT_TYPES:
        if account_type.replace("_", " ") in normalized:
            return account_type
    return "UNKNOWN"


def _account_identity(row: dict[str, str], columns: dict[str, str]) -> tuple[str, str]:
    account_number = row.get(columns.get("account_number", ""), "").strip()
    account_label = row.get(columns.get("account", ""), "").strip()
    account_type_value = row.get(columns.get("account_type", ""), "").strip()
    account_type = _account_type(account_type_value, account_label)
    identifier = account_number or account_label or account_type_value or "default-account"
    return identifier, account_type


def _fingerprint(secret: bytes, value: str) -> str:
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    row_number: int | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "row_number": row_number,
        "field": field,
    }


def _field_columns(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    normalized: dict[str, str] = {}
    for original in headers:
        key = _header(original)
        if key in normalized:
            raise ValueError(f"Duplicate column after normalization: {original}")
        normalized[key] = original

    columns: dict[str, str] = {}
    for semantic, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                columns[semantic] = normalized[alias]
                break
    used = set(columns.values())
    ignored = [header for header in headers if header not in used]
    return columns, ignored


def parse_holdings_csv(content: bytes, *, secret: bytes) -> ImportResult:
    """Parse one Wealthsimple-style holdings CSV into sanitized draft rows."""
    text = _decode_csv(content).replace("\x00", "")
    try:
        dialect = csv.Sniffer().sniff(text[:8_192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
    if not headers:
        raise ValueError("The CSV has no header row")
    columns, ignored = _field_columns(headers)
    missing = [field for field in ("symbol", "quantity") if field not in columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    source_as_of: str | None = None
    skipped_non_holding_rows = 0
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_IMPORT_ROWS:
            raise ValueError(f"The import exceeds the {MAX_IMPORT_ROWS}-row limit")
        row = {str(key or "").strip(): str(value or "").strip() for key, value in raw_row.items()}
        if not any(row.values()):
            continue

        raw_symbol = row.get(columns["symbol"], "").strip().upper()
        raw_quantity = row.get(columns["quantity"], "").strip()
        holding_signals = (
            row.get(columns.get(field, ""), "").strip()
            for field in ("asset_type", "exchange", "currency", "price", "book_value", "market_value")
        )
        if not raw_symbol and not raw_quantity and not any(holding_signals):
            skipped_non_holding_rows += 1
            continue

        account_identifier, account_type = _account_identity(row, columns)
        account_fingerprint = _fingerprint(secret, account_identifier)
        account_alias = f"{account_type}-{account_fingerprint[:4].upper()}"
        security_name = row.get(columns.get("security_name", ""), "").strip() or raw_symbol
        provided_exchange = row.get(columns.get("exchange", ""), "").strip()
        currency = row.get(columns.get("currency", ""), "").strip().upper()
        provided_asset_type = row.get(columns.get("asset_type", ""), "").strip()
        parse_issues: list[dict[str, Any]] = []

        try:
            quantity = _parse_decimal(row.get(columns["quantity"]), required=True)
            if quantity is None or quantity <= 0:
                raise ValueError("quantity must be greater than zero")
        except ValueError as exc:
            quantity = None
            parse_issues.append(
                _issue("error", "MALFORMED_QUANTITY", str(exc), row_number=index, field="quantity")
            )

        average_cost = None
        if "average_cost" in columns:
            try:
                average_cost = _parse_decimal(row.get(columns["average_cost"]))
            except ValueError as exc:
                parse_issues.append(
                    _issue(
                        "error", "MALFORMED_AVERAGE_COST", str(exc), row_number=index, field="average_cost"
                    )
                )

        book_value = None
        if "book_value" in columns:
            try:
                book_value = _parse_decimal(row.get(columns["book_value"]))
            except ValueError as exc:
                parse_issues.append(
                    _issue("warning", "MALFORMED_BOOK_VALUE", str(exc), row_number=index, field="book_value")
                )
        if average_cost is None and book_value is not None and quantity and quantity > 0:
            average_cost = book_value / quantity
            parse_issues.append(
                _issue(
                    "warning",
                    "AVERAGE_COST_DERIVED",
                    "Average cost was calculated as book value divided by quantity.",
                    row_number=index,
                    field="average_cost",
                )
            )

        imported_price = None
        if "price" in columns:
            try:
                imported_price = _parse_decimal(row.get(columns["price"]))
            except ValueError as exc:
                parse_issues.append(
                    _issue("warning", "MALFORMED_IMPORTED_PRICE", str(exc), row_number=index, field="price")
                )

        imported_market_value = None
        if "market_value" in columns:
            try:
                imported_market_value = _parse_decimal(row.get(columns["market_value"]))
            except ValueError as exc:
                parse_issues.append(
                    _issue(
                        "warning", "MALFORMED_MARKET_VALUE", str(exc), row_number=index, field="market_value"
                    )
                )

        if source_as_of is None and "as_of" in columns:
            source_as_of = row.get(columns["as_of"], "").strip() or None

        rows.append(
            {
                "row_number": index,
                "raw_symbol": raw_symbol,
                "security_name": security_name,
                "provided_exchange": provided_exchange,
                "provided_asset_type": provided_asset_type,
                "trading_currency": currency,
                "quantity": _decimal_text(quantity),
                "average_cost": _decimal_text(average_cost),
                "book_value": _decimal_text(book_value),
                "imported_price": _decimal_text(imported_price),
                "imported_market_value": _decimal_text(imported_market_value),
                "account_fingerprint": account_fingerprint,
                "account_alias": account_alias,
                "account_type": account_type,
                "parse_issues": parse_issues,
            }
        )

    if not rows:
        raise ValueError("The CSV contains no holdings")
    if skipped_non_holding_rows:
        issues.append(
            _issue(
                "warning",
                "NON_HOLDING_ROWS_SKIPPED",
                f"Skipped {skipped_non_holding_rows} account header or summary "
                "row(s) that contained no holding data.",
            )
        )
    if any(_header(column) in PII_HEADERS for column in ignored):
        issues.append(
            _issue(
                "warning",
                "PII_COLUMNS_IGNORED",
                "Personal-information columns were ignored and will not be stored.",
            )
        )
    evaluated_rows, validation_issues = evaluate_rows(rows)
    issues.extend(validation_issues)
    return ImportResult(evaluated_rows, issues, ignored, source_as_of)


def _normalize_asset_type(value: str) -> str | None:
    normalized = _header(value)
    if normalized in {"etf", "exchange traded fund", "fund etf"}:
        return "ETF"
    if normalized in {"stock", "equity", "common stock", "common share", "shares"}:
        return "STOCK"
    if normalized in {"cash", "currency"}:
        return "CASH"
    return None


def _normalize_exchange(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    return EXCHANGE_ALIASES.get(normalized)


def _resolve_identity(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = dict(row)
    issues: list[dict[str, Any]] = []
    row_number = int(row["row_number"])
    symbol = str(row.get("raw_symbol") or "").strip().upper()
    provided_exchange = str(row.get("provided_exchange") or "").strip()
    currency = str(row.get("trading_currency") or "").strip().upper()
    asset_type = _normalize_asset_type(str(row.get("provided_asset_type") or ""))
    exchange = _normalize_exchange(provided_exchange)

    if not symbol:
        issues.append(
            _issue("error", "MISSING_SYMBOL", "Symbol is required.", row_number=row_number, field="symbol")
        )
    if asset_type is None:
        issues.append(
            _issue(
                "error",
                "UNKNOWN_ASSET_TYPE",
                "Choose STOCK, ETF or CASH before accepting the import.",
                row_number=row_number,
                field="asset_type",
            )
        )

    canonical_symbol = None
    if asset_type == "CASH":
        exchange = "CASH"
        if symbol not in {"CAD", "USD"}:
            issues.append(
                _issue(
                    "error",
                    "UNSUPPORTED_CASH_CURRENCY",
                    "Cash rows must use CAD or USD as the symbol.",
                    row_number=row_number,
                    field="symbol",
                )
            )
        elif currency and currency != symbol:
            issues.append(
                _issue(
                    "error",
                    "CASH_CURRENCY_CONFLICT",
                    f"Cash symbol {symbol} conflicts with currency {currency}.",
                    row_number=row_number,
                    field="currency",
                )
            )
        else:
            currency = symbol
            canonical_symbol = f"CASH-{symbol}"
    else:
        embedded_exchange: str | None = None
        if symbol.startswith("TSX:"):
            symbol, embedded_exchange = symbol[4:], "TSX"
        elif symbol.startswith("TSXV:"):
            symbol, embedded_exchange = symbol[5:], "TSXV"
        elif symbol.startswith("CVE:"):
            symbol, embedded_exchange = symbol[4:], "TSXV"
        elif symbol.endswith(".TO"):
            symbol, embedded_exchange = symbol[:-3], "TSX"
        elif symbol.endswith(".V"):
            symbol, embedded_exchange = symbol[:-2], "TSXV"
        elif symbol.endswith(".US"):
            symbol, embedded_exchange = symbol[:-3], "US"

        if embedded_exchange and exchange and embedded_exchange != exchange:
            issues.append(
                _issue(
                    "error",
                    "CONFLICTING_EXCHANGE",
                    f"Symbol implies {embedded_exchange}, but the exchange column says {exchange}.",
                    row_number=row_number,
                    field="exchange",
                )
            )
        exchange = embedded_exchange or exchange
        if not exchange:
            issues.append(
                _issue(
                    "error",
                    "AMBIGUOUS_EXCHANGE",
                    "Choose TSX, TSXV or US; a bare ticker is never guessed.",
                    row_number=row_number,
                    field="exchange",
                )
            )

        expected_currency = "CAD" if exchange in {"TSX", "TSXV"} else "USD" if exchange == "US" else None
        if currency not in {"CAD", "USD"}:
            if expected_currency:
                currency = expected_currency
                issues.append(
                    _issue(
                        "warning",
                        "CURRENCY_FROM_EXCHANGE",
                        f"Trading currency was set to {currency} from the explicit exchange.",
                        row_number=row_number,
                        field="currency",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "error",
                        "MISSING_CURRENCY",
                        "Choose CAD or USD.",
                        row_number=row_number,
                        field="currency",
                    )
                )
        elif expected_currency and currency != expected_currency:
            issues.append(
                _issue(
                    "error",
                    "CURRENCY_EXCHANGE_CONFLICT",
                    f"{exchange} is expected to trade in {expected_currency}, not {currency}.",
                    row_number=row_number,
                    field="currency",
                )
            )

        if symbol and exchange == "TSX":
            canonical_symbol = f"{symbol}.TO"
        elif symbol and exchange == "TSXV":
            canonical_symbol = f"{symbol}.V"
        elif symbol and exchange == "US":
            canonical_symbol = symbol

    combined_issues = [*row.get("parse_issues", []), *issues]

    result.update(
        canonical_symbol=canonical_symbol,
        exchange=exchange,
        asset_type=asset_type,
        trading_currency=currency,
        issues=combined_issues,
        resolution_status="resolved"
        if canonical_symbol
        and asset_type
        and not any(item["severity"] == "error" for item in combined_issues)
        else "needs_review",
    )
    return result, result["issues"]


def evaluate_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evaluated: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        resolved, row_issues = _resolve_identity(row)
        evaluated.append(resolved)
        issues.extend(row_issues)
        symbol = resolved.get("canonical_symbol")
        if not symbol:
            continue
        key = (str(resolved["account_fingerprint"]), str(symbol))
        if key in seen:
            duplicate = _issue(
                "error",
                "DUPLICATE_HOLDING",
                f"This account and security duplicate row {seen[key]}.",
                row_number=int(resolved["row_number"]),
                field="symbol",
            )
            resolved["issues"].append(duplicate)
            issues.append(duplicate)
        else:
            seen[key] = int(resolved["row_number"])
    return evaluated, issues


def apply_overrides(
    rows: list[dict[str, Any]], overrides: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_row = {int(item["row_number"]): item for item in overrides}
    updated: list[dict[str, Any]] = []
    for existing in rows:
        row = dict(existing)
        override = by_row.get(int(row["row_number"]), {})
        if override.get("symbol") is not None:
            row["raw_symbol"] = str(override["symbol"]).strip().upper()
        if override.get("exchange") is not None:
            row["provided_exchange"] = str(override["exchange"]).strip()
        if override.get("asset_type") is not None:
            row["provided_asset_type"] = str(override["asset_type"]).strip()
        if override.get("currency") is not None:
            row["trading_currency"] = str(override["currency"]).strip().upper()
        for key in ("canonical_symbol", "exchange", "asset_type", "issues", "resolution_status"):
            row.pop(key, None)
        updated.append(row)
    return evaluate_rows(updated)
