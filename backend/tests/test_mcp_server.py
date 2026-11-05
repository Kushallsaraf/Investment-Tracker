from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.database import Database
from app.mcp_server import NOT_AVAILABLE, create_server, mark_missing
from app.services.container import Services, build_services
from app.services.mcp_setup import READ_TOOLS as SETUP_READ_TOOLS
from app.services.mcp_setup import WRITE_TOOLS as SETUP_WRITE_TOOLS
from app.services.mcp_setup import setup_info
from fakes import FakeHistory, FakePrices, FakeSec, listing, synthetic_bars
from mcp.server.mcpserver.exceptions import ToolError

BARS = synthetic_bars(300, base=100, step=0.5)
READ_TOOLS = {
    "get_quote",
    "get_chart_summary",
    "get_fundamentals",
    "get_peers",
    "get_insider_activity",
    "get_news_sentiment",
    "get_my_notes",
    "get_watchlist",
    "get_position",
}
WRITE_TOOLS = {"add_note", "add_to_watchlist", "save_exit_plan"}


class StaticNews:
    def headlines(self, symbol: str) -> dict[str, Any]:
        item = {
            "title": "Acme wins a large contract",
            "summary": None,
            "url": "https://example.com/acme",
            "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "publisher": "Wire",
            "feed": "Yahoo Finance",
        }
        return {"items": [item], "failures": {}, "fetched_at": item["published_at"]}


class OfflineSec(FakeSec):
    def _call(self, name: str, argument: Any = None) -> None:
        raise ConnectionError("sec.gov is unreachable")


def _services(tmp_path: Path, sec: Any = None) -> Services:
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": BARS},
            "WATCH": {"meta": listing("Watchlist Only Inc."), "bars": BARS},
        }
    )
    return build_services(
        Database(tmp_path / "mcp.sqlite3"),
        history=history,
        prices=FakePrices(),
        sec_client=sec or FakeSec(),
        news=StaticNews(),
        scorer=None,
    )


def _call(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error, result.content
    return result.structured_content


def test_only_research_tools_are_exposed_and_none_can_trade(tmp_path: Path) -> None:
    server = create_server(_services(tmp_path))
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    assert all(tools[name].annotations.read_only_hint for name in READ_TOOLS)
    assert not any(tools[name].annotations.read_only_hint for name in WRITE_TOOLS)
    trading = re.compile(r"\b(order|trade|buy|sell|execute|broker)", re.IGNORECASE)
    assert not any(trading.search(name) for name in tools)


def test_read_tools_carry_dates_and_explicit_missing_markers(tmp_path: Path) -> None:
    services = _services(tmp_path)
    services.portfolio.upsert_position(
        symbol="ACME", quantity="3", average_cost="90", account_name="Brokerage"
    )
    server = create_server(services)

    quote = _call(server, "get_quote", symbol="acme")
    assert (quote["symbol"], quote["last"], quote["as_of"]) == ("ACME", BARS[-1]["close"], BARS[-1]["date"])
    assert quote["price_type"].startswith("daily close")
    assert quote["retrieved_at"]

    setup = _call(server, "get_chart_summary", symbol="ACME")
    assert setup["as_of"] == BARS[-1]["date"]
    assert setup["trend"]["label"] == "Uptrend"

    position = _call(server, "get_position", symbol="ACME")
    assert (position["held"], position["quantity"], position["account"]) == (True, "3", "Brokerage")
    assert position["active_exit_plan"] == NOT_AVAILABLE
    assert position["decision"] == NOT_AVAILABLE
    assert position["price_as_of"]

    unheld = _call(server, "get_position", symbol="WATCH")
    assert unheld["held"] is False

    fundamentals = _call(server, "get_fundamentals", symbol="ACME")
    assert fundamentals["symbol"] == "ACME"
    assert "None" not in repr(fundamentals)

    with pytest.raises(ToolError, match="not a supported US ticker"):
        asyncio.run(server.call_tool("get_quote", {"symbol": "XIC.TO"}))
    with pytest.raises(ToolError, match="between 30 and 365"):
        asyncio.run(server.call_tool("get_insider_activity", {"symbol": "ACME", "days": 5}))


def test_news_sentiment_marks_missing_scores(tmp_path: Path) -> None:
    server = create_server(_services(tmp_path))
    news = _call(server, "get_news_sentiment", symbol="ACME")
    assert news["headlines"][0]["title"] == "Acme wins a large contract"
    assert news["headlines"][0]["sentiment"] == NOT_AVAILABLE
    assert news["sentiment"]["available"] is False
    assert "not installed" in news["sentiment"]["reason"]
    assert news["fetched_at"] != NOT_AVAILABLE


def test_unreachable_sources_are_reported_as_not_available(tmp_path: Path) -> None:
    server = create_server(_services(tmp_path, OfflineSec()))
    insiders = _call(server, "get_insider_activity", symbol="ACME")
    assert insiders["status"] == NOT_AVAILABLE
    assert "unreachable" in insiders["reason"]
    assert insiders["symbol"] == "ACME"


def test_write_tools_only_add_notes_watchlist_items_and_proposals(tmp_path: Path) -> None:
    services = _services(tmp_path)
    server = create_server(services)

    note = _call(server, "add_note", symbol="WATCH", text="Watching the 200-day average.")
    assert note["note"]["author"] == "CLAUDE"
    assert _call(server, "add_to_watchlist", symbol="watch")["symbol"] == "WATCH"
    assert [row["symbol"] for row in services.market.watchlist()["items"]] == ["WATCH"]

    saved = _call(
        server,
        "save_exit_plan",
        symbol="WATCH",
        reasoning="Resistance near the target.",
        target_price=BARS[-1]["close"] + 20,
        stop_price=BARS[-1]["close"] - 15,
        review_date="2099-01-02",
    )
    assert saved["status"] == "proposed"
    assert (saved["plan"]["status"], saved["plan"]["proposed_by"]) == ("PROPOSED", "CLAUDE")
    assert saved["plan"]["decided_at"] == NOT_AVAILABLE
    # A proposal changes nothing until it is accepted in the dashboard.
    journal = services.journal.symbol_journal("WATCH")
    assert journal["triggers"] == []
    assert journal["decision"] is None
    assert services.exit_plans.active("WATCH") is None

    with pytest.raises(ToolError, match="above the stop"):
        asyncio.run(server.call_tool(
            "save_exit_plan",
            {"symbol": "WATCH", "reasoning": "Inverted.", "target_price": 10, "stop_price": 20},
        ))


def test_full_stock_analysis_prompt_names_the_ticker(tmp_path: Path) -> None:
    server = create_server(_services(tmp_path))
    prompts = asyncio.run(server.list_prompts())
    listed = [(prompt.name, prompt.title) for prompt in prompts]
    assert listed == [("full_stock_analysis", "Full stock analysis")]
    result = asyncio.run(server.get_prompt("full_stock_analysis", {"ticker": "brk-b"}))
    text = result.messages[0].content.text
    assert text.startswith("Analyze BRK.B")
    assert "<!--" not in text
    assert "save_exit_plan" in text


def test_mark_missing_is_recursive() -> None:
    assert mark_missing({"a": None, "b": [1, None], "c": {"d": None}}) == {
        "a": NOT_AVAILABLE,
        "b": [1, NOT_AVAILABLE],
        "c": {"d": NOT_AVAILABLE},
    }


def test_setup_info_matches_the_registered_tools(tmp_path: Path) -> None:
    assert set(SETUP_READ_TOOLS) == READ_TOOLS
    assert set(SETUP_WRITE_TOOLS) == WRITE_TOOLS
    info = setup_info()
    server = info["config"]["mcpServers"]["investment-tracker"]
    assert server["args"] == ["-m", "app.mcp_server"]
    assert server["env"]["PYTHONPATH"].endswith("/backend")
    assert Path(server["command"]).name.startswith("python")
    assert info["checks"]["mcp_package"]["ok"] is True
