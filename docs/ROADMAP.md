# Roadmap

Phases build on each other in order. Each phase ships with synthetic-data tests,
explicit "not available" states, and no trading actions.

## Done

- **US-only focus.** Manual and demo portfolios in USD; SnapTrade, CAD, and FX removed.
- **Terminal shell.** Terminal and Portfolio tabs, ticker search, market strip, watchlist.
- **Chart.** Cached daily Yahoo history, TradingView candle/line chart, overlays,
  RSI/MACD pane, and a Python-computed technical setup panel.
- **Redesign.** The Terminal tab is now Research. The Graphite theme puts the chart
  first with six summary cards, and detail (and every Portfolio view) opens in
  side drawers.

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

## Phase 5: Exit plans and the Claude Desktop MCP server (built, except the 5c schedule)

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
  in an Exit plan panel on Research and a review queue in Portfolio → Decisions.
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

### 5c. Optional daily price check (command built; launchd schedule not started)

- A `portfolio-manager-check` command refreshes daily bars for symbols with active
  triggers, evaluates them, and sends a macOS notification (`osascript`) with the
  symbol, level, and reasoning.
- An opt-in macOS `launchd` agent runs it once a day after the US close. It is off
  by default, with an install and uninstall script. There is no real-time feed, so
  daily is the honest cadence.

## Phase 6: News and sentiment (built)

- Headlines from free RSS feeds and SEC 8-K filings; FinBERT scores run locally,
  with a 7-day trend. Adds the `get_news_sentiment` MCP tool.

## Phase 7: Macro (built)

- World and economy headlines grouped by theme (war and geopolitics, trade, energy,
  the Fed, inflation, jobs, China, growth, policy) and linked to the holdings in
  each theme's sectors.
- Upcoming market-moving reports from FRED's release calendar plus FOMC meetings.
- Latest economic data from FRED (free API key).
- Adds the `get_macro_snapshot` MCP tool. The sector heatmap was dropped as not
  worth the space.

## Optional: Plain-English macro explainers (undecided)

FinBERT only labels sentiment, so explanations need a generative model. The default
is Qwen 2.5 7B through Ollama, which runs on this Mac for free and keeps everything
local. If built, this becomes the first piece of Phase 8.

- **Story grouping.** Group the week's headlines into stories by theme and similar
  wording, so each story gets one explainer.
- **Headlines only, stated plainly.** The model works from the story's headlines and
  feed summaries, not the full articles, and every explainer says so. No extra data
  is added to the prompt, to keep a local model fast. The one exception is the
  holdings in the story's sectors, needed for "what it means for you".
- **Model connection.** A small Ollama client with the model set in `.env` (default
  `qwen2.5:7b`), built so a cloud model can be added later.
- **Explainer format.** What happened, why, why markets care, what it means for you,
  what to watch, a term to know, and sources. Generated when clicked, then saved,
  so it's instant the next time. Labelled AI-generated; never buy or sell advice;
  says so when the headlines don't explain why.
- **Interface.** An "Explain" button on each story in the Macro drawer, plus a short
  "Why this matters to me" line on each theme.
- **Claude prompt.** "Explain this week's macro news" in the MCP server, using the
  existing tools under the Claude Pro plan.
- **Tests.** A fake model to check the format, the rules (no buy or sell advice,
  sources required), caching, and the "Ollama isn't running" message.

## Phase 8: In-app AI analyst panel (built)

- Chat about the ticker on screen through Ollama (default `qwen2.5:7b`) or any
  OpenAI-compatible cloud API, streamed as it's written.
- Grounded in a compact fact pack the investor can inspect; answers cite the
  numbers, never compute prices or signals, and never give buy or sell advice.
- Quick prompts, stop, and save-to-notes. The optional macro explainers above
  would reuse this model connection.

## Phase 9: Strategy engine and backtests

- Plain-English strategies translated into confirmed rule checklists, evaluated in
  code on the chart, and backtested on daily history with costs, next-open fills,
  and small-sample warnings. Adds the `run_strategy` MCP tool.

## Phase 10: Portfolio polish and presentation

- CI on GitHub Actions, a hosted demo with the synthetic portfolio (no MCP),
  screenshots and an architecture diagram in the README.
