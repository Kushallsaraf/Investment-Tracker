"""What the dashboard shows about connecting Claude Desktop to the local MCP server."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVER_NAME = "investment-tracker"
PROMPT_TITLE = "Full stock analysis"
SEC_PLACEHOLDER = "Your Name your.email@example.com"
SEC_HINT = "Replace the placeholder with your name and email"

# The MCP server registers exactly these; a test keeps the two lists in step.
READ_TOOLS: dict[str, str] = {
    "get_quote": "Latest daily close and change",
    "get_chart_summary": "Trend, RSI, MACD, ATR, 52-week range, strength vs SPY",
    "get_fundamentals": "Valuation, growth and margins from SEC filings",
    "get_peers": "Side-by-side comparison with peers",
    "get_insider_activity": "Open-market insider buys and sales (Form 4)",
    "get_news_sentiment": "Recent headlines, local FinBERT sentiment, 7-day trend, and 8-K filings",
    "get_my_notes": "Your notes, decision, review triggers and exit plans",
    "get_watchlist": "Watchlist tickers with their latest close",
    "get_position": "Your position, decision and accepted exit plan",
}
WRITE_TOOLS: dict[str, str] = {
    "add_note": "Saves a note labeled as written by Claude",
    "add_to_watchlist": "Adds a ticker to the watchlist",
    "save_exit_plan": "Saves an exit plan as a proposal you accept or reject here",
}


def _python_path() -> Path:
    """The project virtualenv's interpreter, which is what Claude Desktop should launch."""
    venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    return venv if venv.exists() else Path(sys.executable)


def setup_info() -> dict[str, Any]:
    python = _python_path()
    mcp_installed = importlib.util.find_spec("mcp") is not None
    backend = PROJECT_ROOT / "backend"
    env = {
        "PYTHONPATH": str(backend),
        "PORTFOLIO_MANAGER_SEC_USER_AGENT": settings.sec_user_agent or SEC_PLACEHOLDER,
    }
    # Point Claude at the same data folder when the app runs with a custom one.
    if str(settings.runtime_root) != str((Path.home() / ".portfolio-manager").resolve()):
        env["PORTFOLIO_MANAGER_HOME"] = str(settings.runtime_root)
    return {
        "server_name": SERVER_NAME,
        "config": {
            "mcpServers": {
                SERVER_NAME: {"command": str(python), "args": ["-m", "app.mcp_server"], "env": env}
            }
        },
        "checks": {
            "python": {"ok": python.exists(), "detail": str(python)},
            "mcp_package": {
                "ok": mcp_installed,
                "detail": "Installed" if mcp_installed else "Run: .venv/bin/pip install -e .",
            },
            "sec_contact": {
                "ok": settings.sec_user_agent is not None,
                "detail": "Set" if settings.sec_user_agent else SEC_HINT,
            },
        },
        "data_folder": str(settings.runtime_root),
        "config_file": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "read_tools": READ_TOOLS,
        "write_tools": WRITE_TOOLS,
        "prompt": PROMPT_TITLE,
    }
