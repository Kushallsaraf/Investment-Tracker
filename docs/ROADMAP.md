# Roadmap

Phases build on each other in order. Each phase ships with synthetic-data tests,
explicit "not available" states, and no trading actions.

## Done

- **US-only focus.** Manual and demo portfolios in USD; SnapTrade, CAD, and FX removed.
- **Terminal shell.** Terminal and Portfolio tabs, ticker search, market strip, watchlist.
- **Chart.** Cached daily Yahoo history, TradingView candle/line chart, overlays,
  RSI/MACD pane, and a Python-computed technical setup panel.

## Phase 3: SEC EDGAR data (built and checked against live SEC data)

- Map tickers to SEC CIKs from `company_tickers.json`; send the User-Agent with a
  contact email that SEC requires, read from local configuration.
- **Fundamentals** from `companyfacts`: market cap, valuation multiples, growth,
  margins, free cash flow, debt, and valuation against the company's own history.
  ETFs show top holdings instead.
- **Insider activity** from Form 4 filings: buys, sells, 10b5-1 plans, net 90 days.
- **Peers** seeded from the SIC industry code and editable.
- Cache filings in SQLite with fetched-at and filing dates on every value.

## Phase 4: Notes and a shared symbol identity (built)

- Notes per ticker, optionally pinned to a chart date and drawn as chart markers.
- **Shared identity.** Today journal tables (decisions, review triggers) are keyed by
  holdings `instrument_id`, so a watchlist-only ticker cannot have a trigger. Create
  the instrument record on demand for any Terminal symbol so notes, decisions, and
  exit plans work whether or not the ticker is held.
- Add a 20-day moving average to the technical setup so it reports 20/50/200.

Moved ahead of news and macro because the MCP server depends on notes.

## Phase 5: Exit plans and the Claude Desktop MCP server

Depends on: chart and technical setup (done), fundamentals and peers (Phase 3),
notes and shared identity (Phase 4), the existing decision journal and review triggers.

Local only: works with Claude Desktop on this Mac under the Claude Pro plan, not in a
hosted demo. The in-app AI analyst panel (Ollama plus a free cloud tier) is unchanged.

### 5a. Exit plans in the dashboard (built first, so the MCP tool has a destination)

- New `exit_plans` table: symbol, target price, stop price, review date, reasoning,
  `proposed_by` (`CLAUDE` or `USER`), status (`PROPOSED`, `ACCEPTED`, `REJECTED`,
  `SUPERSEDED`), created and decided timestamps.
- A Claude proposal is labeled "Proposed by Claude" and never changes the investor's
  decision. This follows the existing rule that a Claude suggestion is not a decision.
- **Accepting a proposal (in the UI only):**
  - Creates `PRICE_ABOVE` (target), `PRICE_BELOW` (stop), and `DATE` (review)
    triggers through the existing review-trigger service.
  - Saves the reasoning as a dated note.
  - Records a decision-history entry with `claude_disposition = ACCEPTED`.
  - Rejected proposals stay in history for reference.
- Accepted target and stop are drawn as price lines on the chart. Proposals appear
  in an Exit plan panel on the Terminal and a review queue in Portfolio → Decisions.
- **Trigger evaluation from cached daily bars**, not only holding valuations, so
  watchlist tickers are covered. When a level is crossed or the review date
  arrives, the alert shows the original reasoning.

### 5b. MCP server

- `backend/app/mcp_server.py` using the official `mcp` Python SDK (FastMCP, stdio).
  It calls the existing services and SQLite database directly, with no duplicated
  logic. It never writes to stdout except protocol messages (logs go to stderr).
- **Read tools.** Every response carries as-of dates and explicit `NOT AVAILABLE`
  markers:
  - `get_quote` / `get_chart_summary`: price, trend vs 20/50/200 MAs, RSI, ATR,
    52-week range position, strength vs SPY, volume vs average.
  - `get_fundamentals`, `get_peers`, `get_insider_activity`.
  - `get_my_notes`, `get_watchlist`, `get_position` (quantity, cost basis, account,
    current decision, active exit plan).
  - Added when their phases land: `get_news_sentiment`, `get_macro_snapshot`,
    `run_strategy(symbol, strategy)`.
- **Write tools,** limited to notes, the watchlist, and exit plans:
  - `add_note(symbol, text)`
  - `add_to_watchlist(symbol)`
  - `save_exit_plan(symbol, target_price, stop_price, review_date, reasoning)`
    always stores a `PROPOSED` plan; only the dashboard can accept it.
  - No tool can place, simulate, or describe an order.
- **Prompt:** "Full stock analysis" with a `ticker` argument, using placeholder text
  until the real prompt is supplied. It ends by offering to save an exit plan.
- **Setup:** a sample `claude_desktop_config.json` (path to `.venv/bin/python`,
  `-m app.mcp_server`, `PYTHONPATH` set to `backend`) and README setup steps.
- **Tests:** call the tools in-process against a synthetic database and fake
  providers; assert as-of fields, `NOT AVAILABLE` markers, and that write tools can
  only create proposals.

### 5c. Optional daily price check

- A `portfolio-manager-check` command refreshes daily bars for symbols with active
  triggers, evaluates them, and sends a macOS notification (`osascript`) with the
  symbol, level, and reasoning.
- An opt-in macOS `launchd` agent runs it once a day after the US close. It is off
  by default, with an install and uninstall script. There is no real-time feed, so
  daily is the honest cadence.

## Phase 6: News and sentiment

- Headlines from free RSS feeds and SEC 8-K filings; FinBERT scores run locally,
  with a 7-day trend. Adds the `get_news_sentiment` MCP tool.

## Phase 7: Macro and markets

- Sector ETF heatmap; Fed funds, yield curve, and CPI from FRED (free API key);
  economic calendar. Adds the `get_macro_snapshot` MCP tool.

## Phase 8: In-app AI analyst panel

- Provider layer for Ollama and a free cloud tier, fed the same fact pack as the
  panels. Answers cite the on-screen numbers and never compute prices or signals.

## Phase 9: Strategy engine and backtests

- Plain-English strategies translated into confirmed rule checklists, evaluated in
  code on the chart, and backtested on daily history with costs, next-open fills,
  and small-sample warnings. Adds the `run_strategy` MCP tool.

## Phase 10: Portfolio polish and presentation

- CI on GitHub Actions, a hosted demo with the synthetic portfolio (no MCP),
  screenshots and an architecture diagram in the README.
