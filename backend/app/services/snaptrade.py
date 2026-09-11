"""Two-step, read-only Wealthsimple synchronization through SnapTrade Personal."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.importers.wealthsimple import load_or_create_secret
from app.integrations.snaptrade import (
    SnapTradeCredentialsUnavailable,
    SnapTradeError,
    SnapTradeReadClient,
)
from app.repository import PortfolioRepository
from app.services.portfolio import PortfolioService

SYNC_PREVIEW_STALE_AFTER = timedelta(hours=36)
SUPPORTED_ACCOUNT_TYPES = ("TFSA", "RRSP", "FHSA", "RESP", "LIRA", "RRIF")
CANADIAN_EXCHANGES = {
    "TSX": ("TSX", ".TO"),
    "XTSE": ("TSX", ".TO"),
    "TSE": ("TSX", ".TO"),
    "TSXV": ("TSXV", ".V"),
    "XTSX": ("TSXV", ".V"),
    "CVE": ("TSXV", ".V"),
}
US_EXCHANGES = {"US", "XNAS", "NASDAQ", "XNYS", "NYSE", "ARCX", "ARCA", "BATS"}


class SnapTradeSyncError(RuntimeError):
    """A safe, user-facing synchronization error."""


class SnapTradeSyncRateLimited(SnapTradeSyncError):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(
            "Holdings synchronization is limited to once every 10 minutes. "
            f"Try again in {self.retry_after} seconds."
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _oldest_timestamp(values: list[str]) -> str | None:
    parsed = [item for value in values if (item := _datetime(value)) is not None]
    return min(parsed).isoformat() if parsed else None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _scalar(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if nested not in (None, ""):
                return str(nested).strip()
        return ""
    return str(value or "").strip()


def _account_type(account: dict[str, Any]) -> str:
    source = f"{account.get('raw_type') or ''} {account.get('name') or ''}".upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", source)
    for account_type in SUPPORTED_ACCOUNT_TYPES:
        if account_type in normalized:
            return account_type
    return "UNKNOWN"


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    symbol: str | None = None,
) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "symbol": symbol}


class SnapTradeSyncService:
    def __init__(
        self,
        repository: PortfolioRepository,
        portfolio: PortfolioService,
        client: SnapTradeReadClient,
        *,
        enabled: bool,
        redirect_uri: str,
        local_secret_path: Any,
        min_sync_seconds: int = 600,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.repository = repository
        self.portfolio = portfolio
        self.client = client
        self.enabled = enabled
        self.redirect_uri = redirect_uri
        self.local_secret_path = local_secret_path
        self.min_sync_seconds = max(600, int(min_sync_seconds))
        self.clock = clock

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise SnapTradeSyncError(
                "SnapTrade is disabled. Complete the security audit and Keychain setup first."
            )

    def status(self) -> dict[str, Any]:
        state = self.repository.snaptrade_state()
        now = self.clock()
        last_attempt = _datetime(state.get("last_attempted_sync_at"))
        next_allowed = (
            last_attempt + timedelta(seconds=self.min_sync_seconds) if last_attempt else None
        )
        status = str(state.get("connection_status") or "not_checked")
        warnings = [state["warning"]] if state.get("warning") else []
        holdings_as_of = _datetime(state.get("holdings_as_of"))
        stale = bool(holdings_as_of and holdings_as_of < now - SYNC_PREVIEW_STALE_AFTER)
        if stale:
            warnings.append(
                "SnapTrade holdings are more than 36 hours old. Verify the holdings as-of time."
            )
        if status == "disabled_connection":
            warnings.append(
                "The Wealthsimple connection is disabled; SnapTrade may return only cached data."
            )
        return {
            "adapter_enabled": self.enabled,
            "connection_status": "adapter_disabled" if not self.enabled else status,
            "connection_permission": state.get("connection_permission"),
            "brokerage_name": state.get("brokerage_name") or "Wealthsimple",
            "last_checked_at": state.get("last_checked_at"),
            "last_attempted_sync_at": state.get("last_attempted_sync_at"),
            "last_successful_sync_at": state.get("last_successful_sync_at"),
            "holdings_as_of": state.get("holdings_as_of"),
            "next_sync_allowed_at": next_allowed.isoformat() if next_allowed else None,
            "sync_allowed": bool(self.enabled and (next_allowed is None or now >= next_allowed)),
            "stale": stale,
            "warnings": list(dict.fromkeys(warnings)),
        }

    def _record_credentials_missing(self) -> None:
        self.repository.update_snaptrade_state(
            connection_status="credentials_missing",
            warning="SnapTrade credentials are not available from macOS Keychain.",
        )

    def create_portal(self) -> str:
        self._require_enabled()
        status = str(self.repository.snaptrade_state().get("connection_status") or "")
        if status == "connected_read_only":
            raise SnapTradeSyncError(
                "Wealthsimple is already connected read-only. Use Sync instead of opening "
                "another authentication session."
            )
        if status == "disconnect_pending":
            raise SnapTradeSyncError(
                "SnapTrade is still processing the previous disconnection. Use Check Status "
                "and wait until it reports Not Connected before reconnecting."
            )
        try:
            return self.client.create_connection_portal(self.redirect_uri)
        except SnapTradeCredentialsUnavailable:
            self._record_credentials_missing()
            raise SnapTradeSyncError(
                "SnapTrade credentials are not available from macOS Keychain."
            ) from None
        except SnapTradeError as exc:
            raise SnapTradeSyncError(str(exc)) from exc

    def check_connection(self) -> dict[str, Any]:
        """Refresh connection state without requesting accounts or holdings."""
        self._require_enabled()
        try:
            connections = [
                row for row in self.client.list_connections() if self._is_wealthsimple(row)
            ]
        except SnapTradeCredentialsUnavailable:
            self._record_credentials_missing()
            return self.status()
        except SnapTradeError as exc:
            raise SnapTradeSyncError(str(exc)) from exc

        checked_at = self.clock().isoformat()
        previous = str(
            self.repository.snaptrade_state().get("connection_status") or "not_checked"
        )
        if previous == "disconnect_pending":
            updates: dict[str, Any] = {
                "connection_status": "disconnect_pending" if connections else "not_connected",
                "connection_permission": None,
                "brokerage_name": "Wealthsimple",
                "last_checked_at": checked_at,
                "warning": (
                    "SnapTrade is still processing the Wealthsimple disconnection."
                    if connections
                    else None
                ),
            }
            if not connections:
                updates["connection_fingerprint"] = None
            self.repository.update_snaptrade_state(**updates)
            return self.status()

        if not connections:
            self.repository.update_snaptrade_state(
                connection_status="not_connected",
                connection_permission=None,
                brokerage_name="Wealthsimple",
                connection_fingerprint=None,
                last_checked_at=checked_at,
                warning=None,
            )
            return self.status()

        unsafe = [row for row in connections if str(row.get("type") or "").lower() != "read"]
        active = [row for row in connections if not bool(row.get("disabled"))]
        disabled = [row for row in connections if bool(row.get("disabled"))]
        if unsafe:
            connection_status = "rejected_trade_enabled"
            permission = str(unsafe[0].get("type") or "unknown")
            warning = "A non-read-only Wealthsimple connection was rejected."
        elif not active:
            connection_status = "disabled_connection"
            permission = "read"
            warning = "Every Wealthsimple connection reported by SnapTrade is disabled."
        else:
            connection_status = "connected_read_only"
            permission = "read"
            warning = (
                "One or more additional Wealthsimple connections are disabled."
                if disabled
                else None
            )
        self.repository.update_snaptrade_state(
            connection_status=connection_status,
            connection_permission=permission,
            brokerage_name="Wealthsimple",
            last_checked_at=checked_at,
            warning=warning,
        )
        return self.status()

    @staticmethod
    def _is_wealthsimple(connection: dict[str, Any]) -> bool:
        brokerage = connection.get("brokerage") or {}
        identity = " ".join(
            [
                _scalar(brokerage, "slug"),
                _scalar(brokerage, "name"),
                _scalar(brokerage, "display_name"),
            ]
        ).lower()
        return "wealthsimple" in identity

    def _read_connections(self) -> list[dict[str, Any]]:
        try:
            connections = [row for row in self.client.list_connections() if self._is_wealthsimple(row)]
        except SnapTradeCredentialsUnavailable:
            self._record_credentials_missing()
            raise SnapTradeSyncError(
                "SnapTrade credentials are not available from macOS Keychain."
            ) from None
        except SnapTradeError as exc:
            raise SnapTradeSyncError(str(exc)) from exc

        checked_at = self.clock().isoformat()
        if not connections:
            self.repository.update_snaptrade_state(
                connection_status="not_connected",
                connection_permission=None,
                brokerage_name="Wealthsimple",
                connection_fingerprint=None,
                last_checked_at=checked_at,
                warning=None,
            )
            raise SnapTradeSyncError("No Wealthsimple connection was found in SnapTrade.")

        unsafe = [row for row in connections if str(row.get("type") or "").lower() != "read"]
        if unsafe:
            self.repository.update_snaptrade_state(
                connection_status="rejected_trade_enabled",
                connection_permission=str(unsafe[0].get("type") or "unknown"),
                brokerage_name="Wealthsimple",
                last_checked_at=checked_at,
                warning=(
                    "A non-read-only Wealthsimple connection was rejected. "
                    "Portfolio data was not requested."
                ),
            )
            raise SnapTradeSyncError(
                "A non-read-only Wealthsimple connection was rejected; holdings were not accessed."
            )

        disabled = [row for row in connections if bool(row.get("disabled"))]
        active = [row for row in connections if not bool(row.get("disabled"))]
        fingerprint_source = ":".join(sorted(str(row.get("id") or "") for row in connections))
        secret = load_or_create_secret(self.local_secret_path)
        fingerprint = hmac.new(
            secret, fingerprint_source.encode(), hashlib.sha256
        ).hexdigest()
        if not active:
            self.repository.update_snaptrade_state(
                connection_status="disabled_connection",
                connection_permission="read",
                brokerage_name="Wealthsimple",
                connection_fingerprint=fingerprint,
                last_checked_at=checked_at,
                warning="Every Wealthsimple connection reported by SnapTrade is disabled.",
            )
            raise SnapTradeSyncError(
                "The Wealthsimple connection is disabled; reconnect it before synchronizing."
            )
        self.repository.update_snaptrade_state(
            connection_status="connected_read_only",
            connection_permission="read",
            brokerage_name="Wealthsimple",
            connection_fingerprint=fingerprint,
            last_checked_at=checked_at,
            warning=(
                "One or more additional Wealthsimple connections are disabled."
                if disabled
                else None
            ),
        )
        return active

    def _enforce_sync_interval(self) -> None:
        state = self.repository.snaptrade_state()
        last_attempt = _datetime(state.get("last_attempted_sync_at"))
        now = self.clock()
        if last_attempt and now < last_attempt + timedelta(seconds=self.min_sync_seconds):
            remaining = int(
                (last_attempt + timedelta(seconds=self.min_sync_seconds) - now).total_seconds()
            )
            raise SnapTradeSyncRateLimited(remaining)
        self.repository.update_snaptrade_state(last_attempted_sync_at=now.isoformat())

    @staticmethod
    def _exchange_and_symbol(
        raw_symbol: str,
        currency: str,
        exchange_value: str,
    ) -> tuple[str | None, str | None]:
        symbol = raw_symbol.strip().upper()
        exchange = exchange_value.strip().upper()
        if not symbol:
            return None, None
        if symbol.endswith(".TO"):
            return "TSX", symbol
        if symbol.endswith(".V"):
            return "TSXV", symbol
        if currency == "CAD" and exchange in CANADIAN_EXCHANGES:
            normalized, suffix = CANADIAN_EXCHANGES[exchange]
            return normalized, f"{symbol}{suffix}"
        if currency == "USD" and exchange in US_EXCHANGES:
            return "US", symbol
        return None, None

    def _normalize_position(
        self,
        position: dict[str, Any],
        *,
        account_fingerprint: str,
        account_alias: str,
        account_type: str,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        instrument = position.get("instrument") or {}
        raw_symbol = _scalar(instrument.get("symbol"), "symbol", "raw_symbol") or _scalar(
            instrument.get("raw_symbol"), "symbol", "raw_symbol"
        )
        kind = _scalar(instrument.get("kind")).lower()
        if bool(position.get("cash_equivalent")):
            issues.append(
                _issue(
                    "warning",
                    "CASH_EQUIVALENT_SKIPPED",
                    "A cash-equivalent position was skipped to avoid double-counting account cash.",
                    symbol=raw_symbol or None,
                )
            )
            return None
        asset_type = "ETF" if kind == "etf" else "STOCK" if kind in {"stock", "adr"} else None
        if asset_type is None:
            issues.append(
                _issue(
                    "error",
                    "UNSUPPORTED_INSTRUMENT",
                    f"{raw_symbol or 'Unknown instrument'} has unsupported type {kind or 'missing'}.",
                    symbol=raw_symbol or None,
                )
            )
            return None
        currency = (
            _scalar(position.get("currency"), "code")
            or _scalar(instrument.get("currency"), "code")
        ).upper()
        if currency not in {"CAD", "USD"}:
            issues.append(
                _issue(
                    "error",
                    "UNSUPPORTED_CURRENCY",
                    f"{raw_symbol or 'Unknown instrument'} has missing or unsupported currency.",
                    symbol=raw_symbol or None,
                )
            )
            return None
        exchange_value = _scalar(instrument.get("exchange"), "code", "mic", "name")
        exchange, canonical_symbol = self._exchange_and_symbol(
            raw_symbol, currency, exchange_value
        )
        if exchange is None or canonical_symbol is None:
            issues.append(
                _issue(
                    "error",
                    "UNRESOLVED_SYMBOL",
                    f"{raw_symbol or 'Unknown instrument'} has an ambiguous exchange; it was not guessed.",
                    symbol=raw_symbol or None,
                )
            )
            return None
        quantity = _decimal(position.get("units"))
        if quantity is None or quantity <= 0:
            issues.append(
                _issue(
                    "error",
                    "INVALID_QUANTITY",
                    f"{canonical_symbol} has a missing or non-positive quantity.",
                    symbol=canonical_symbol,
                )
            )
            return None
        average_cost = _decimal(position.get("cost_basis"))
        if average_cost is not None and average_cost < 0:
            issues.append(
                _issue(
                    "error",
                    "INVALID_COST_BASIS",
                    f"{canonical_symbol} has an invalid cost basis.",
                    symbol=canonical_symbol,
                )
            )
            return None
        if average_cost is None:
            issues.append(
                _issue(
                    "warning",
                    "MISSING_COST_BASIS",
                    f"{canonical_symbol} has no cost basis from Wealthsimple.",
                    symbol=canonical_symbol,
                )
            )
        return {
            "row_number": 0,
            "canonical_symbol": canonical_symbol,
            "security_name": _scalar(instrument.get("description")) or canonical_symbol,
            "asset_type": asset_type,
            "exchange": exchange,
            "trading_currency": currency,
            "quantity": _text(quantity),
            "average_cost": _text(average_cost),
            "account_fingerprint": account_fingerprint,
            "account_alias": account_alias,
            "account_type": account_type,
        }

    @staticmethod
    def _changes(
        current: dict[str, Any] | None,
        incoming: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        current_rows = (current or {}).get("holdings") or []
        old = {
            (row["account_type"], row["canonical_symbol"]): row
            for row in current_rows
        }
        new = {
            (row["account_type"], row["canonical_symbol"]): row
            for row in incoming
        }
        additions: list[dict[str, Any]] = []
        removals: list[dict[str, Any]] = []
        quantity_changes: list[dict[str, Any]] = []
        cost_basis_changes: list[dict[str, Any]] = []
        cash_changes: list[dict[str, Any]] = []

        for key in sorted(new.keys() - old.keys()):
            row = new[key]
            target = cash_changes if row["asset_type"] == "CASH" else additions
            target.append(
                {
                    "symbol": row["canonical_symbol"],
                    "account_type": row["account_type"],
                    "before": None,
                    "after": row["quantity"],
                }
            )
        for key in sorted(old.keys() - new.keys()):
            row = old[key]
            target = cash_changes if row["asset_type"] == "CASH" else removals
            target.append(
                {
                    "symbol": row["canonical_symbol"],
                    "account_type": row["account_type"],
                    "before": row["quantity"],
                    "after": None,
                }
            )
        for key in sorted(old.keys() & new.keys()):
            before = old[key]
            after = new[key]
            if before["asset_type"] == "CASH" or after["asset_type"] == "CASH":
                if _decimal(before.get("quantity")) != _decimal(after.get("quantity")):
                    cash_changes.append(
                        {
                            "symbol": after["canonical_symbol"],
                            "account_type": after["account_type"],
                            "before": before.get("quantity"),
                            "after": after.get("quantity"),
                        }
                    )
                continue
            if _decimal(before.get("quantity")) != _decimal(after.get("quantity")):
                quantity_changes.append(
                    {
                        "symbol": after["canonical_symbol"],
                        "account_type": after["account_type"],
                        "before": before.get("quantity"),
                        "after": after.get("quantity"),
                    }
                )
            if _decimal(before.get("average_cost")) != _decimal(after.get("average_cost")):
                cost_basis_changes.append(
                    {
                        "symbol": after["canonical_symbol"],
                        "account_type": after["account_type"],
                        "before": before.get("average_cost"),
                        "after": after.get("average_cost"),
                    }
                )
        return {
            "additions": additions,
            "removals": removals,
            "quantity_changes": quantity_changes,
            "cost_basis_changes": cost_basis_changes,
            "cash_changes": cash_changes,
        }

    @staticmethod
    def _public_preview(preview: dict[str, Any]) -> dict[str, Any]:
        issues = preview["issues"]
        return {
            "preview_id": preview["id"],
            "created_at": preview["created_at"],
            "expires_at": preview["expires_at"],
            "holdings_as_of": preview["holdings_as_of"],
            "last_successful_sync_at": preview["last_successful_sync_at"],
            "positions": [
                {key: value for key, value in row.items() if key != "account_fingerprint"}
                for row in preview["rows"]
            ],
            "changes": preview["changes"],
            "issues": issues,
            "error_count": sum(issue["severity"] == "error" for issue in issues),
            "warning_count": sum(issue["severity"] == "warning" for issue in issues),
            "can_apply": not any(issue["severity"] == "error" for issue in issues),
        }

    def _reconcile_known_instrument_identities(
        self, preview: dict[str, Any]
    ) -> dict[str, Any]:
        """Keep established local identity when a brokerage asset label disagrees."""
        current = self.portfolio.latest()
        known = {
            row["canonical_symbol"]: {
                "asset_type": row["asset_type"],
                "exchange": row["exchange"],
                "trading_currency": row["trading_currency"],
            }
            for row in (current or {}).get("holdings") or []
        }
        rows = [dict(row) for row in preview["rows"]]
        issues = [dict(issue) for issue in preview["issues"]]
        existing_issues = {(issue.get("code"), issue.get("symbol")) for issue in issues}

        for row in rows:
            symbol = row["canonical_symbol"]
            identity = known.get(symbol)
            if identity is None:
                continue
            if (
                row["exchange"] != identity["exchange"]
                or row["trading_currency"] != identity["trading_currency"]
            ):
                key = ("STORED_IDENTITY_CONFLICT", symbol)
                if key not in existing_issues:
                    issues.append(
                        _issue(
                            "error",
                            key[0],
                            f"{symbol} conflicts with its stored exchange or currency; "
                            "the identity must be reviewed before applying.",
                            symbol=symbol,
                        )
                    )
                    existing_issues.add(key)
                continue
            if row["asset_type"] != identity["asset_type"]:
                reported_type = row["asset_type"]
                row["asset_type"] = identity["asset_type"]
                key = ("BROKERAGE_ASSET_TYPE_CONFLICT", symbol)
                if key not in existing_issues:
                    issues.append(
                        _issue(
                            "warning",
                            key[0],
                            f"SnapTrade classified {symbol} as {reported_type}; the existing "
                            f"local {identity['asset_type']} classification was retained.",
                            symbol=symbol,
                        )
                    )
                    existing_issues.add(key)

        return {**preview, "rows": rows, "issues": issues}

    def preview_sync(self) -> dict[str, Any]:
        self._require_enabled()
        self._enforce_sync_interval()
        connections = self._read_connections()
        connection_ids = {str(row.get("id") or "") for row in connections}
        try:
            accounts = [
                row
                for row in self.client.list_accounts()
                if str(row.get("brokerage_authorization") or "") in connection_ids
            ]
        except SnapTradeError as exc:
            raise SnapTradeSyncError(str(exc)) from exc
        if not accounts:
            raise SnapTradeSyncError("The read-only Wealthsimple connection returned no accounts.")

        local_secret = load_or_create_secret(self.local_secret_path)
        rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        holdings_times: list[str] = []
        successful_sync_times: list[str] = []
        seen: set[tuple[str, str]] = set()

        for account in accounts:
            account_id = str(account.get("id") or "")
            account_type = _account_type(account)
            fingerprint = hmac.new(
                local_secret,
                f"snaptrade-account:{account_id}".encode(),
                hashlib.sha256,
            ).hexdigest()
            alias = f"{account_type}-{fingerprint[:4].upper()}"
            sync_status = (account.get("sync_status") or {}).get("holdings") or {}
            if sync_status.get("last_successful_sync"):
                successful_sync_times.append(str(sync_status["last_successful_sync"]))
            if bool(sync_status.get("holdings_unavailable")):
                issues.append(
                    _issue(
                        "error",
                        "HOLDINGS_UNAVAILABLE",
                        f"{alias} does not expose holdings through SnapTrade.",
                    )
                )
                continue
            if account_type == "UNKNOWN":
                issues.append(
                    _issue(
                        "warning",
                        "UNKNOWN_ACCOUNT_TYPE",
                        f"{alias} has an unrecognized account type.",
                    )
                )
            try:
                position_payload = self.client.list_positions(account_id)
                balances = self.client.list_balances(account_id)
            except SnapTradeError as exc:
                issues.append(_issue("error", "ACCOUNT_READ_FAILED", str(exc)))
                continue
            data_freshness = position_payload.get("data_freshness") or {}
            if data_freshness.get("as_of"):
                holdings_times.append(str(data_freshness["as_of"]))
            for position in position_payload.get("results") or []:
                if position.get("as_of"):
                    holdings_times.append(str(position["as_of"]))
                normalized = self._normalize_position(
                    position,
                    account_fingerprint=fingerprint,
                    account_alias=alias,
                    account_type=account_type,
                    issues=issues,
                )
                if normalized is None:
                    continue
                key = (fingerprint, normalized["canonical_symbol"])
                if key in seen:
                    issues.append(
                        _issue(
                            "error",
                            "DUPLICATE_POSITION",
                            f"{normalized['canonical_symbol']} appeared more than once in {alias}.",
                            symbol=normalized["canonical_symbol"],
                        )
                    )
                    continue
                seen.add(key)
                rows.append(normalized)
            for balance in balances:
                currency = _scalar(balance.get("currency"), "code").upper()
                cash = _decimal(balance.get("cash"))
                if cash in (None, Decimal("0")):
                    continue
                if currency not in {"CAD", "USD"} or cash is None or cash < 0:
                    issues.append(
                        _issue(
                            "error",
                            "UNSUPPORTED_CASH_BALANCE",
                            f"{alias} has an unsupported or negative cash balance.",
                        )
                    )
                    continue
                symbol = f"CASH-{currency}"
                key = (fingerprint, symbol)
                if key in seen:
                    issues.append(
                        _issue(
                            "error",
                            "DUPLICATE_CASH_BALANCE",
                            f"{symbol} appeared more than once in {alias}.",
                            symbol=symbol,
                        )
                    )
                    continue
                seen.add(key)
                rows.append(
                    {
                        "row_number": 0,
                        "canonical_symbol": symbol,
                        "security_name": currency,
                        "asset_type": "CASH",
                        "exchange": "CASH",
                        "trading_currency": currency,
                        "quantity": _text(cash),
                        "average_cost": "1",
                        "account_fingerprint": fingerprint,
                        "account_alias": alias,
                        "account_type": account_type,
                    }
                )

        rows.sort(key=lambda row: (row["account_alias"], row["canonical_symbol"]))
        for index, row in enumerate(rows, start=1):
            row["row_number"] = index
        holdings_as_of = _oldest_timestamp(holdings_times)
        last_successful = _oldest_timestamp(successful_sync_times)
        if holdings_as_of is None:
            issues.append(
                _issue(
                    "warning",
                    "MISSING_HOLDINGS_AS_OF",
                    "SnapTrade did not provide a holdings as-of timestamp.",
                )
            )
        elif (_datetime(holdings_as_of) or self.clock()) < self.clock() - SYNC_PREVIEW_STALE_AFTER:
            issues.append(
                _issue(
                    "warning",
                    "STALE_HOLDINGS",
                    "SnapTrade holdings are more than 36 hours old.",
                )
            )
        reconciled = self._reconcile_known_instrument_identities(
            {"rows": rows, "issues": issues}
        )
        rows = reconciled["rows"]
        issues = reconciled["issues"]
        changes = self._changes(self.portfolio.latest(), rows)
        preview = self.repository.create_snaptrade_preview(
            rows=rows,
            changes=changes,
            issues=issues,
            holdings_as_of=holdings_as_of,
            last_successful_sync_at=last_successful,
        )
        self.repository.update_snaptrade_state(
            connection_status="connected_read_only",
            connection_permission="read",
            brokerage_name="Wealthsimple",
            last_successful_sync_at=last_successful,
            holdings_as_of=holdings_as_of,
        )
        return self._public_preview(preview)

    def apply_preview(self, preview_id: str) -> dict[str, str]:
        self._require_enabled()
        preview = self._reconcile_known_instrument_identities(
            self.repository.snaptrade_preview(preview_id)
        )
        snapshot_id = self.repository.persist_snaptrade_preview(
            preview_id,
            rows_override=preview["rows"],
            issues_override=preview["issues"],
        )
        valuation_id = self.portfolio.refresh(snapshot_id)
        return {"holding_snapshot_id": snapshot_id, "valuation_snapshot_id": valuation_id}

    def pending_preview(self) -> dict[str, Any] | None:
        """Recover a local preview without making a new brokerage request."""
        preview = self.repository.latest_snaptrade_preview()
        if preview is None:
            return None
        return self._public_preview(self._reconcile_known_instrument_identities(preview))

    def cancel_preview(self, preview_id: str) -> None:
        self.repository.delete_snaptrade_preview(preview_id)

    def disconnect(self) -> int:
        self._require_enabled()
        try:
            connections = [row for row in self.client.list_connections() if self._is_wealthsimple(row)]
            for connection in connections:
                self.client.disconnect(str(connection.get("id") or ""))
        except SnapTradeCredentialsUnavailable:
            self._record_credentials_missing()
            raise SnapTradeSyncError(
                "SnapTrade credentials are not available from macOS Keychain."
            ) from None
        except SnapTradeError as exc:
            raise SnapTradeSyncError(str(exc)) from exc
        self.repository.update_snaptrade_state(
            connection_status="disconnect_pending" if connections else "not_connected",
            connection_permission=None,
            last_checked_at=self.clock().isoformat(),
            warning=(
                "SnapTrade is processing the Wealthsimple disconnection."
                if connections
                else None
            ),
        )
        return len(connections)

    def delete_local_data(self) -> int:
        return self.repository.delete_local_snaptrade_data()
