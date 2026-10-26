"""Strictly allowlisted, read-only access to SnapTrade Personal.

This module intentionally does not depend on SnapTrade's general-purpose SDK.
Only connection setup/status, accounts, positions, balances, completed account
activities, and disconnection exist in this client. Secrets are read from macOS Keychain and are never
accepted from an API request or persisted by Portfolio Manager.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

import httpx

KEYCHAIN_SERVICE = "com.portfolio-manager.snaptrade"
CLIENT_ID_ACCOUNT = "client-id"
CONSUMER_KEY_ACCOUNT = "consumer-key"
SNAPTRADE_API_ROOT = "https://api.snaptrade.com"

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_UUID_VALUE = re.compile(rf"^{_UUID}$")
_ALLOWED_ENDPOINTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/snapTrade/login$")),
    ("GET", re.compile(r"^/authorizations$")),
    ("GET", re.compile(r"^/accounts$")),
    ("GET", re.compile(rf"^/accounts/{_UUID}/positions/all$")),
    ("GET", re.compile(rf"^/accounts/{_UUID}/balances$")),
    ("GET", re.compile(rf"^/accounts/{_UUID}/activities$")),
    ("DELETE", re.compile(rf"^/connection/{_UUID}$")),
)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SnapTradeError(RuntimeError):
    """A redacted integration error safe to display in the local UI."""


class SnapTradeCredentialsUnavailable(SnapTradeError):
    """The Personal API credentials are not available from Keychain."""


class SnapTradeEndpointRejected(SnapTradeError):
    """A request was blocked by the read-only endpoint allowlist."""


@dataclass(frozen=True, repr=False)
class SnapTradeCredentials:
    client_id: str
    consumer_key: str

    def __repr__(self) -> str:
        return "SnapTradeCredentials(client_id=<redacted>, consumer_key=<redacted>)"


class CredentialProvider(Protocol):
    def load(self) -> SnapTradeCredentials: ...


class SnapTradeReadClient(Protocol):
    def create_connection_portal(self, redirect_uri: str) -> str: ...

    def list_connections(self) -> list[dict[str, Any]]: ...

    def list_accounts(self) -> list[dict[str, Any]]: ...

    def list_positions(self, account_id: str) -> dict[str, Any]: ...

    def list_balances(self, account_id: str) -> list[dict[str, Any]]: ...

    def list_activities(
        self,
        account_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        offset: int = 0,
        limit: int = 1_000,
    ) -> dict[str, Any]: ...

    def disconnect(self, connection_id: str) -> None: ...


class MacOSKeychainCredentialProvider:
    """Read credentials from Keychain without accepting or printing values."""

    @staticmethod
    def _read(account: str) -> str:
        try:
            result = subprocess.run(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-s",
                    KEYCHAIN_SERVICE,
                    "-a",
                    account,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SnapTradeCredentialsUnavailable(
                "SnapTrade credentials are unavailable in macOS Keychain"
            ) from exc
        value = result.stdout.strip()
        if result.returncode != 0 or not value:
            raise SnapTradeCredentialsUnavailable(
                "SnapTrade credentials are unavailable in macOS Keychain"
            )
        return value

    def load(self) -> SnapTradeCredentials:
        return SnapTradeCredentials(
            client_id=self._read(CLIENT_ID_ACCOUNT),
            consumer_key=self._read(CONSUMER_KEY_ACCOUNT),
        )


class ReadOnlySnapTradeClient:
    """Minimal Personal API client whose transport is deny-by-default."""

    def __init__(
        self,
        credentials: CredentialProvider,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._credentials = credentials
        self._client = client or httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "Portfolio-Manager/0.2 (local read-only portfolio sync)"},
        )
        self._clock = clock

    @staticmethod
    def _assert_allowed(method: str, path: str) -> None:
        normalized_method = method.upper()
        if not any(
            normalized_method == allowed_method and pattern.fullmatch(path)
            for allowed_method, pattern in _ALLOWED_ENDPOINTS
        ):
            raise SnapTradeEndpointRejected("SnapTrade request blocked by read-only allowlist")

    @staticmethod
    def _signature(path: str, query: str, body: dict[str, Any] | None, key: str) -> str:
        payload = {
            "content": None if not body else body,
            "path": path,
            "query": query,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest = hmac.new(key.encode(), canonical.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    @staticmethod
    def _safe_request_id(response: httpx.Response) -> str | None:
        """Return only a bounded, non-sensitive correlation ID from SnapTrade."""
        for header in ("x-request-id", "x-correlation-id"):
            value = response.headers.get(header, "").strip()
            if value and _SAFE_REQUEST_ID.fullmatch(value):
                return value
        return None

    @classmethod
    def _http_error(cls, response: httpx.Response, operation: str) -> SnapTradeError:
        request_id = cls._safe_request_id(response)
        reference = f" SnapTrade request ID: {request_id}." if request_id else ""
        if response.status_code == 404 and operation == "connection portal request":
            return SnapTradeError(
                "SnapTrade could not create the Connection Portal (404). "
                "In Keychain Access, verify that the client-id item contains the Client ID "
                "from a Personal API Key and that consumer-key is the matching Consumer Key. "
                "Do not share either value."
                f"{reference}"
            )
        return SnapTradeError(
            f"SnapTrade {operation} failed ({response.status_code}).{reference}"
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query_params: list[tuple[str, str]] | None = None,
        operation: str,
    ) -> Any:
        self._assert_allowed(method, path)
        credentials = self._credentials.load()
        parameters = [
            ("clientId", credentials.client_id),
            ("timestamp", str(int(self._clock()))),
        ]
        parameters.extend(query_params or [])
        query = urlencode(parameters)
        signature = self._signature(path, query, body, credentials.consumer_key)
        request_kwargs: dict[str, Any] = {
            "headers": {"Signature": signature, "Accept": "application/json"},
        }
        if body is not None:
            request_kwargs["json"] = body
        try:
            response = self._client.request(
                method.upper(),
                f"{SNAPTRADE_API_ROOT}{path}?{query}",
                **request_kwargs,
            )
        except httpx.HTTPError as exc:
            raise SnapTradeError(f"SnapTrade {operation} is temporarily unavailable") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise self._http_error(response, operation)
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise SnapTradeError(f"SnapTrade {operation} returned an invalid response") from exc

    def create_connection_portal(self, redirect_uri: str) -> str:
        parsed = urlsplit(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise SnapTradeError("Connection return address must be a local Portfolio Manager URL")
        payload = self._request(
            "POST",
            "/snapTrade/login",
            body={
                "connectionType": "read",
                "customRedirect": redirect_uri,
            },
            operation="connection portal request",
        )
        redirect = str((payload or {}).get("redirectURI") or "")
        target = urlsplit(redirect)
        if target.scheme != "https" or not (
            target.hostname == "snaptrade.com" or str(target.hostname).endswith(".snaptrade.com")
        ):
            raise SnapTradeError("SnapTrade returned an invalid connection portal address")
        return redirect

    def list_connections(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/authorizations", operation="connection check")
        if not isinstance(payload, list):
            raise SnapTradeError("SnapTrade connection check returned an invalid response")
        return [item for item in payload if isinstance(item, dict)]

    def list_accounts(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/accounts", operation="account synchronization")
        if not isinstance(payload, list):
            raise SnapTradeError("SnapTrade accounts returned an invalid response")
        return [item for item in payload if isinstance(item, dict)]

    def list_positions(self, account_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/positions/all",
            operation="position synchronization",
        )
        if not isinstance(payload, dict):
            raise SnapTradeError("SnapTrade positions returned an invalid response")
        return payload

    def list_balances(self, account_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/balances",
            operation="balance synchronization",
        )
        if not isinstance(payload, list):
            raise SnapTradeError("SnapTrade balances returned an invalid response")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _activity_date(value: str | None, field: str) -> str | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as exc:
            raise SnapTradeEndpointRejected(f"Invalid {field} for activities request") from exc

    def list_activities(
        self,
        account_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        offset: int = 0,
        limit: int = 1_000,
    ) -> dict[str, Any]:
        """List completed daily/cached activities using strictly bounded parameters."""
        if not _UUID_VALUE.fullmatch(account_id):
            raise SnapTradeEndpointRejected("Invalid account identifier for activities request")
        normalized_start = self._activity_date(start_date, "start date")
        normalized_end = self._activity_date(end_date, "end date")
        if normalized_start and normalized_end and normalized_start > normalized_end:
            raise SnapTradeEndpointRejected("Activities start date must not follow end date")
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 100_000:
            raise SnapTradeEndpointRejected("Activities offset is outside the allowed range")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000:
            raise SnapTradeEndpointRejected("Activities limit is outside the allowed range")
        query_params: list[tuple[str, str]] = []
        if normalized_start:
            query_params.append(("startDate", normalized_start))
        if normalized_end:
            query_params.append(("endDate", normalized_end))
        query_params.extend((("offset", str(offset)), ("limit", str(limit))))
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/activities",
            query_params=query_params,
            operation="completed activity synchronization",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SnapTradeError("SnapTrade activities returned an invalid response")
        pagination = payload.get("pagination") or {}
        if not isinstance(pagination, dict):
            raise SnapTradeError("SnapTrade activities returned invalid pagination")
        return {
            "data": [item for item in payload["data"] if isinstance(item, dict)],
            "pagination": pagination,
        }

    def disconnect(self, connection_id: str) -> None:
        self._request(
            "DELETE",
            f"/connection/{connection_id}",
            operation="connection removal",
        )
