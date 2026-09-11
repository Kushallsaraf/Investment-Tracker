from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from app.database import Database
from app.integrations.snaptrade import (
    ReadOnlySnapTradeClient,
    SnapTradeCredentials,
    SnapTradeEndpointRejected,
    SnapTradeError,
)
from app.repository import PortfolioRepository
from app.services.portfolio import PortfolioService
from app.services.snaptrade import SnapTradeSyncError, SnapTradeSyncService

CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
ACCOUNT_ID = "22222222-2222-4222-8222-222222222222"


class SyntheticCredentials:
    def load(self) -> SnapTradeCredentials:
        return SnapTradeCredentials("SYNTHETIC_CLIENT_ID", "SYNTHETIC_CONSUMER_KEY")


def test_personal_client_signs_only_allowlisted_read_operations() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/snapTrade/login"):
            body = json.loads(request.content)
            assert body["connectionType"] == "read"
            assert "broker" not in body
            assert "userId" not in body
            assert "userSecret" not in body
            return httpx.Response(
                200,
                json={"redirectURI": "https://app.snaptrade.com/synthetic-portal"},
            )
        if request.url.path.endswith("/authorizations"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/accounts"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/positions/all"):
            return httpx.Response(200, json={"results": []})
        if request.url.path.endswith("/balances"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith(f"/connection/{CONNECTION_ID}"):
            return httpx.Response(200, json={"detail": "queued"})
        raise AssertionError(f"Unexpected synthetic request path: {request.url.path}")

    client = ReadOnlySnapTradeClient(
        SyntheticCredentials(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: 1_789_000_000,
    )
    client.create_connection_portal("http://127.0.0.1:5173/?snaptrade=connected")
    client.list_connections()
    client.list_accounts()
    client.list_positions(ACCOUNT_ID)
    client.list_balances(ACCOUNT_ID)
    client.disconnect(CONNECTION_ID)

    assert {request.method for request in requests} == {"GET", "POST", "DELETE"}
    for request in requests:
        assert request.url.host == "api.snaptrade.com"
        assert not request.url.path.startswith("/api/v1/")
        query = parse_qs(request.url.query.decode())
        assert query["clientId"] == ["SYNTHETIC_CLIENT_ID"]
        assert "timestamp" in query
        assert request.headers.get("Signature")
        serialized = request.content.decode(errors="ignore")
        assert "SYNTHETIC_CONSUMER_KEY" not in str(request.url)
        assert "SYNTHETIC_CONSUMER_KEY" not in serialized

    portal_request = requests[0]
    portal_query = portal_request.url.query.decode()
    portal_body = json.loads(portal_request.content)
    expected_signature = ReadOnlySnapTradeClient._signature(  # noqa: SLF001
        "/snapTrade/login",
        portal_query,
        portal_body,
        "SYNTHETIC_CONSUMER_KEY",
    )
    assert portal_request.headers["Signature"] == expected_signature


def test_deny_by_default_transport_blocks_every_non_allowlisted_endpoint() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = ReadOnlySnapTradeClient(
        SyntheticCredentials(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    blocked = [
        ("POST", "/trade/place"),
        ("POST", f"/accounts/{ACCOUNT_ID}/orders/cancel"),
        ("PATCH", f"/accounts/{ACCOUNT_ID}"),
        ("GET", f"/accounts/{ACCOUNT_ID}/orders"),
    ]
    for method, path in blocked:
        with pytest.raises(SnapTradeEndpointRejected):
            client._request(method, path, operation="blocked test")  # noqa: SLF001
    assert calls == 0


def test_client_exposes_only_read_data_and_connection_operations() -> None:
    public_methods = {
        name
        for name, value in inspect.getmembers(ReadOnlySnapTradeClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {
        "create_connection_portal",
        "disconnect",
        "list_accounts",
        "list_balances",
        "list_connections",
        "list_positions",
    }


def test_snaptrade_error_does_not_echo_response_body_or_request_url() -> None:
    response_marker = "SENSITIVE-SYNTHETIC-RESPONSE"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": response_marker})

    client = ReadOnlySnapTradeClient(
        SyntheticCredentials(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SnapTradeError) as captured:
        client.list_connections()
    message = str(captured.value)
    assert response_marker not in message
    assert "SYNTHETIC_CLIENT_ID" not in message
    assert "SYNTHETIC_CONSUMER_KEY" not in message


def test_portal_404_gives_safe_keychain_guidance_without_echoing_response() -> None:
    response_marker = "SENSITIVE-SYNTHETIC-RESPONSE"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            headers={"x-request-id": "safe-synthetic-request-123"},
            json={"detail": response_marker},
        )

    client = ReadOnlySnapTradeClient(
        SyntheticCredentials(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SnapTradeError) as captured:
        client.create_connection_portal("http://127.0.0.1:5173/?snaptrade=connected")
    message = str(captured.value)
    assert "Personal API Key" in message
    assert "Keychain Access" in message
    assert "safe-synthetic-request-123" in message
    assert response_marker not in message
    assert "SYNTHETIC_CLIENT_ID" not in message
    assert "SYNTHETIC_CONSUMER_KEY" not in message


def test_untrusted_request_id_is_not_displayed() -> None:
    unsafe_request_id = "unsafe request id containing secret-marker"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"x-request-id": unsafe_request_id}, json={})

    client = ReadOnlySnapTradeClient(
        SyntheticCredentials(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SnapTradeError) as captured:
        client.create_connection_portal("http://localhost:5173/?snaptrade=connected")
    assert unsafe_request_id not in str(captured.value)


def test_credentials_have_a_redacted_representation() -> None:
    credentials = SnapTradeCredentials("VISIBLE-NOWHERE", "SECRET-NOWHERE")
    assert "VISIBLE-NOWHERE" not in repr(credentials)
    assert "SECRET-NOWHERE" not in repr(credentials)


class NoPrices:
    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError(f"Prices must not be fetched for rejected connection: {instrument}")


class NoFx:
    def usd_cad(self) -> dict[str, Any]:
        raise AssertionError("FX must not be fetched for a rejected connection")


class UnsafeConnectionFixture:
    def __init__(self) -> None:
        self.account_calls = 0

    def create_connection_portal(self, redirect_uri: str) -> str:
        raise AssertionError(redirect_uri)

    def list_connections(self) -> list[dict[str, Any]]:
        return [
            {
                "id": CONNECTION_ID,
                "type": "trade",
                "disabled": False,
                "brokerage": {"slug": "WEALTHSIMPLE"},
            }
        ]

    def list_accounts(self) -> list[dict[str, Any]]:
        self.account_calls += 1
        return []

    def list_positions(self, account_id: str) -> dict[str, Any]:
        raise AssertionError(account_id)

    def list_balances(self, account_id: str) -> list[dict[str, Any]]:
        raise AssertionError(account_id)

    def disconnect(self, connection_id: str) -> None:
        raise AssertionError(connection_id)


def test_non_read_only_connection_is_rejected_before_account_access(tmp_path: Path) -> None:
    repository = PortfolioRepository(Database(tmp_path / "rejected.sqlite3"))
    portfolio = PortfolioService(repository, price_provider=NoPrices(), fx_provider=NoFx())
    fixture = UnsafeConnectionFixture()
    service = SnapTradeSyncService(
        repository,
        portfolio,
        fixture,
        enabled=True,
        redirect_uri="http://127.0.0.1:5173/?snaptrade=connected",
        local_secret_path=tmp_path / "alias.key",
        clock=lambda: datetime(2026, 9, 10, 15, tzinfo=UTC),
    )

    with pytest.raises(SnapTradeSyncError, match="non-read-only"):
        service.preview_sync()
    assert fixture.account_calls == 0
    assert service.status()["connection_status"] == "rejected_trade_enabled"


def test_application_has_no_order_or_trading_api_routes() -> None:
    from app.main import app

    paths = {route.path for route in app.routes}
    assert not any("order" in path.lower() for path in paths)
    assert not any(path.startswith("/api/trade") for path in paths)


def test_snaptrade_schema_has_no_credential_columns(tmp_path: Path) -> None:
    database = Database(tmp_path / "schema.sqlite3")
    with database.connect() as connection:
        table_names = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'snaptrade%'"
            )
        ]
        columns = {
            str(row["name"]).lower()
            for table in table_names
            for row in connection.execute(f"PRAGMA table_info({table})")  # noqa: S608
        }
    assert "client_id" not in columns
    assert "consumer_key" not in columns
    assert "userid" not in columns
    assert "usersecret" not in columns
