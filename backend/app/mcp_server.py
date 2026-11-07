"""Claude Desktop MCP server for Investment Tracker (stdio, local only).

Claude gets read access to the same data the dashboard shows, and three write tools: add a
note, add to the watchlist, and propose an exit plan. A proposal never takes effect until the
investor accepts it in the dashboard. There is no tool that places, simulates, or describes an
order.

stdout carries protocol messages only; logs go to stderr.

Run with:  PYTHONPATH=backend .venv/bin/python -m app.mcp_server
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.providers.prices import UnsupportedSymbolError, normalize_symbol
from app.services.container import Services, build_services

T = TypeVar("T")
NOT_AVAILABLE = "NOT AVAILABLE"
PROMPT_PATH = Path(__file__).with_name("prompts") / "full_stock_analysis.md"

INSTRUCTIONS = """\
Investment Tracker is a personal, research-only tool for US stocks and ETFs, using daily data.
Every figure carries the date it is as of; "NOT AVAILABLE" means the data is missing, so say so
instead of estimating it. Prices are daily closes, not live quotes.
You may add notes, add tickers to the watchlist, and propose exit plans. Exit plans are saved
as proposals that the investor accepts or rejects in the dashboard. Never present anything as
an order or a recommendation to trade.
"""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

logger = logging.getLogger("investment_tracker.mcp")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def mark_missing(value: Any) -> Any:
    """Replace every missing value with an explicit marker so Claude can't mistake it for zero."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, dict):
        return {key: mark_missing(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mark_missing(item) for item in value]
    return value


def _read(action: Callable[[], dict[str, Any]], symbol: str | None = None) -> dict[str, Any]:
    """Run a read tool. Bad tickers are errors; an unreachable data source is reported as data."""
    try:
        payload = action()
    except (UnsupportedSymbolError, ValueError, KeyError) as exc:
        raise ToolError(str(exc.args[0]) if exc.args else str(exc)) from exc
    except Exception as exc:  # network, SEC configuration, provider outages
        logger.warning("Read tool failed for %s: %s", symbol, exc)
        payload = {"status": NOT_AVAILABLE, "reason": f"{type(exc).__name__}: {exc}"}
        if symbol:
            payload["symbol"] = normalize_symbol(symbol)
    return mark_missing({**payload, "retrieved_at": _now()})


def _write(action: Callable[[], T]) -> T:
    try:
        return action()
    except (UnsupportedSymbolError, ValueError, KeyError) as exc:
        raise ToolError(str(exc.args[0]) if exc.args else str(exc)) from exc


def create_server(services: Services | None = None) -> MCPServer:
    svc = services or build_services()
    server = MCPServer(name="investment-tracker", title="Investment Tracker", instructions=INSTRUCTIONS)

    # Read tools

    @server.tool(annotations=READ)
    def get_quote(symbol: str) -> dict[str, Any]:
        """Latest daily close for a US stock or ETF, with its change and the date it is as of."""

        def load() -> dict[str, Any]:
            chart = svc.market.chart(symbol, "1M")
            return {
                "symbol": chart["symbol"],
                "name": chart["name"],
                "exchange": chart["exchange"],
                "asset_type": chart["asset_type"],
                **chart["quote"],
                "stale": chart["stale"],
                "price_type": "daily close (delayed, not a live quote)",
                "source": chart["source"],
                "fetched_at": chart["fetched_at"],
            }

        return _read(load, symbol)

    @server.tool(annotations=READ)
    def get_chart_summary(symbol: str) -> dict[str, Any]:
        """Technical setup from daily closes: trend vs 20/50/200-day averages, RSI, MACD, ATR,
        52-week range position, 3-month strength vs SPY, and volume vs its 20-day average."""
        return _read(lambda: svc.market.technicals(symbol), symbol)

    @server.tool(annotations=READ)
    def get_fundamentals(symbol: str) -> dict[str, Any]:
        """Valuation, growth, margins, and balance sheet from SEC 10-K/10-Q filings, each with its
        as-of date, plus P/E and P/S against the company's own 5-year range."""
        return _read(lambda: svc.fundamentals.fundamentals(symbol), symbol)

    @server.tool(annotations=READ)
    def get_peers(symbol: str) -> dict[str, Any]:
        """Side-by-side valuation, growth, margin, and 3-month return for the ticker and its peers."""
        return _read(lambda: svc.peers.comparison(symbol), symbol)

    @server.tool(annotations=READ)
    def get_insider_activity(symbol: str, days: int = 90) -> dict[str, Any]:
        """Open-market insider buys and sales from SEC Form 4 filings over the last `days` days
        (30 to 365). Grants, option exercises, and tax withholding are excluded from totals."""
        if not 30 <= days <= 365:
            raise ToolError("days must be between 30 and 365")
        return _read(lambda: svc.insiders.activity(symbol, days=days), symbol)

    @server.tool(annotations=READ)
    def get_news_sentiment(symbol: str) -> dict[str, Any]:
        """Recent headlines (Yahoo Finance and Nasdaq RSS) with FinBERT sentiment scored on this
        computer, a 7-day daily trend, and 8-K filings from the last 30 days. Sentiment describes
        the wording of headlines, not the stock."""
        return _read(lambda: svc.news.news(symbol), symbol)

    @server.tool(annotations=READ)
    def get_macro_snapshot() -> dict[str, Any]:
        """The macro picture: latest US economic data (jobs, inflation, rates, yield curve, GDP,
        retail sales, sentiment, oil) with dates, market-moving reports and Fed meetings in the next
        45 days, and this week's world and economy headlines grouped by theme (war and geopolitics,
        trade, energy, the Fed, China and more) with the portfolio holdings each theme usually touches."""
        return _read(svc.macro.snapshot)

    @server.tool(annotations=READ)
    def get_my_notes(symbol: str) -> dict[str, Any]:
        """The investor's notes, current decision, open review triggers, and exit plans for a ticker."""
        return _read(lambda: svc.journal.symbol_journal(symbol), symbol)

    @server.tool(annotations=READ)
    def get_watchlist() -> dict[str, Any]:
        """Tickers on the watchlist with their latest daily close and change."""
        return _read(svc.market.watchlist)

    @server.tool(annotations=READ)
    def get_position(symbol: str) -> dict[str, Any]:
        """The investor's position in a ticker (quantity, cost basis, account, value, weight),
        their current decision, and the accepted exit plan if there is one."""

        def load() -> dict[str, Any]:
            canonical = normalize_symbol(symbol)
            portfolio = svc.portfolio.latest()
            holdings = (portfolio or {}).get("holdings", [])
            holding = next((row for row in holdings if row["canonical_symbol"] == canonical), None)
            journal = svc.journal.symbol_journal(canonical)
            base = {
                "symbol": canonical,
                "held": holding is not None,
                "portfolio_origin": (portfolio or {}).get("data_origin"),
                "decision": journal["decision"],
                "active_exit_plan": svc.exit_plans.active(canonical),
            }
            if holding is None:
                return base
            return {
                **base,
                "account": holding["account_name"],
                "quantity": holding["quantity"],
                "average_cost": holding["average_cost"],
                "price": holding["price"],
                "market_value": holding["market_value"],
                "unrealized_gain_loss": holding["unrealized_gain_loss"],
                "portfolio_weight": holding["portfolio_weight"],
                "price_as_of": holding["price_timestamp"],
                "price_source": holding["price_source"],
                "snapshot_as_of": (portfolio or {}).get("snapshot_created_at"),
            }

        return _read(load, symbol)

    # Write tools: notes, the watchlist, and exit-plan proposals only.

    @server.tool(annotations=WRITE)
    def add_note(symbol: str, text: str) -> dict[str, Any]:
        """Save a note on a ticker, labeled as written by Claude."""
        note = _write(lambda: svc.journal.add_note(symbol, text, author="CLAUDE"))
        return {"status": "saved", "note": mark_missing(note)}

    @server.tool(annotations=WRITE)
    def add_to_watchlist(symbol: str) -> dict[str, Any]:
        """Add a US stock or ETF to the watchlist."""
        added = _write(lambda: svc.market.add_to_watchlist(symbol))
        return {"status": "saved", "symbol": added}

    @server.tool(annotations=WRITE)
    def save_exit_plan(
        symbol: str,
        reasoning: str,
        target_price: float | None = None,
        stop_price: float | None = None,
        review_date: str | None = None,
    ) -> dict[str, Any]:
        """Propose an exit plan: a price target, a stop level, and/or a review date (YYYY-MM-DD),
        with the reasoning. It is saved as a proposal only; the investor accepts or rejects it in
        the dashboard, and accepting it creates review alerts, never orders."""
        plan = _write(
            lambda: svc.exit_plans.propose(
                symbol,
                target_price=target_price,
                stop_price=stop_price,
                review_date=review_date,
                reasoning=reasoning,
                proposed_by="CLAUDE",
            )
        )
        return {
            "status": "proposed",
            "plan": mark_missing(plan),
            "next_step": "Saved as a proposal. It takes effect only if the investor accepts it in "
            "Investment Tracker (Research → Exit plan).",
        }

    @server.prompt(
        name="full_stock_analysis",
        title="Full stock analysis",
        description="Research a ticker with the dashboard's data and offer to save an exit plan.",
    )
    def full_stock_analysis(ticker: str) -> str:
        return render_prompt(ticker)

    return server


def render_prompt(ticker: str) -> str:
    """The analysis prompt for one ticker. HTML comments in the file are notes for the editor."""
    symbol = normalize_symbol(ticker)
    text = re.sub(r"<!--.*?-->\s*", "", PROMPT_PATH.read_text(encoding="utf-8"), flags=re.DOTALL)
    return text.strip().replace("{ticker}", symbol)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    create_server().run("stdio")


if __name__ == "__main__":
    main()
