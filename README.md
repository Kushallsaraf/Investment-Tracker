# Investment Tracker

A standalone, local-first research, portfolio-monitoring, and decision-journal
application for US-listed stocks and ETFs. Holdings are entered manually or loaded
from a synthetic demo portfolio; all values are reported in USD.

The application never connects to a brokerage, never stores brokerage credentials,
and has no order or trading UI.

## Safety boundary

- No brokerage connection. Positions and activities are entered by hand, or loaded
  from a clearly labelled synthetic demo portfolio.
- No order placement, modification, cancellation, or trading routes. Editing a
  holding creates a new local snapshot; it never represents a trade.
- Market data is read-only and fetched from a free daily source. Quotes are
  timestamped and classified as real-time, delayed, end-of-day, or stale.
- Only US listings quoted in USD are accepted. Symbols are verified against the
  price provider before they are stored.
- The app itself calls no AI API. The optional Claude Desktop MCP server runs on
  this computer: Claude can read your research data, add notes and watchlist
  items, and propose exit plans, which do nothing until you accept them in the
  dashboard. No tool can place, simulate, or describe an order.
- Runtime data is stored under `~/.portfolio-manager/` by default with restrictive
  local permissions.

## Portfolio workflow

1. **Add positions** on the Holdings tab: symbol, quantity, optional average cost,
   and an account name (for example "Brokerage" or "Roth IRA"). Enter `CASH` as the
   symbol for USD cash. Saving the same symbol in the same account replaces it.
2. **Or load the demo portfolio** from Settings. It holds illustrative US stocks,
   ETFs, cash, and a year of synthetic activities. It is refused while manual
   holdings or manual activities exist, so real data is never overwritten.
3. **Record activities** (buys, sells, dividends, deposits, withdrawals, fees,
   interest, withholding tax) on the Activity tab. Income is calculated from this
   ledger. Recording a buy or sell does not change holdings.
4. Every change produces a new immutable holdings snapshot and valuation, so the
   history of the portfolio is preserved.

Positions are valued with independently fetched quotes; a missing quote is shown as
missing and excluded from the total rather than estimated.

## Interface

The interface uses one dark theme (Graphite: near-black with a teal accent) and
two top-level tabs. Detail opens in side drawers, so each screen stays short.

**Research** is a single-ticker screen. Open any US stock or ETF from the ticker
search (`⌘K`, `Ctrl K`, or `/`) or the watchlist rail. The header shows a short
market pulse (SPY, QQQ, VIX, and the 10-year yield).

- The chart uses TradingView Lightweight Charts with candle/line views, 1M–MAX
  ranges, an Indicators menu (EMA 20/50, SMA 200, Bollinger, and an RSI or MACD
  pane), and volume. Daily history is cached in SQLite and refreshed at most every
  15 minutes. Accepted exit-plan levels are drawn as price lines.
- Six summary cards open drawers with the detail:
  - **Trend:** RSI, MACD, 52-week range position, 3-month strength against SPY,
    ATR, a 2× ATR stop level, and relative volume. Every indicator is calculated
    in Python; nothing is a signal or forecast.
  - **Valuation:** SEC EDGAR company facts (10-K and 10-Q): market cap, P/E, P/S,
    EV/EBITDA, free-cash-flow yield, growth, margins, net cash, and P/E and P/S
    against the company's own five-year range. Trailing-twelve-month values are
    built from quarterly filings. ETFs show "not applicable".
  - **Insiders:** Form 4 filings from the last 90 days. Open-market buys and sales
    are totaled; grants, exercises, and tax withholding are excluded, and
    pre-planned 10b5-1 sales are marked.
  - **Peers:** seeded from the company's SEC industry code and editable, comparing
    valuation, growth, margins, and 3-month return.
  - **Notes:** notes per ticker, optionally pinned to a date and shown as chart
    markers (click a candle to pin a note there), your decision for any ticker
    (held or not), and its open review triggers.
  - **News:** headlines from the Yahoo Finance and Nasdaq RSS feeds plus 8-K filings
    from the last 30 days, with each 8-K's item numbers translated (for example
    "Earnings results"). Headlines are scored positive, neutral, or negative by
    FinBERT running on this computer, with a 7-day trend. Headlines are cached and
    refetched at most every 30 minutes, and each one is scored once. Sentiment rates
    the wording of headlines, not the stock.
  - **Strategies:** a placeholder until the strategy engine lands.
- **Exit plan** shows Claude's proposals with Accept and Reject, the accepted
  plan, and a form to write your own. See [Exit plans](#exit-plans).
- **Ask AI** is a placeholder for the in-app AI panel.
- **How this works** explains each data source and how fresh it is.

**Macro** (header button) opens a wide drawer with the market-wide picture:

- **This week in the world:** headlines from CNBC (world and economy), MarketWatch,
  and Federal Reserve press releases, grouped into themes such as war and
  geopolitics, trade and tariffs, energy and oil, the Fed and rates, inflation,
  jobs, China, growth, and government policy. Headlines that match no macro theme
  (personal-finance columns, for example) are left out. Each theme shows how many
  headlines it had this week, their FinBERT tone, and the holdings in the sectors
  it usually affects. That link is by sector, so it shows where a theme tends to
  matter, not what will happen.
- **Coming up:** the next 45 days of market-moving reports from FRED's release
  calendar (jobs report, CPI, PCE, GDP, PPI, retail sales, JOLTS, jobless claims,
  consumer sentiment, industrial production) and Fed rate decisions from the
  Federal Reserve's FOMC calendar, each marked high, medium, or low impact.
- **Latest data:** unemployment, payrolls, jobless claims, CPI, core CPI, core
  PCE, the Fed funds target, 2- and 10-year Treasury yields, the 10y–2y spread
  (flagged when inverted), real GDP growth, retail sales, consumer sentiment, and
  WTI oil, each with the period it covers and the change from the prior reading.

**Portfolio** shows the total value, gain, income, price coverage, a sector
allocation bar, and the holdings list. Selecting a holding opens its details with
a link to Research. Toolbar buttons open the detail views as drawers:

- **Edit holdings** is an Excel-style worksheet with an add/update form, saved
  column preferences, editable stock sectors and decisions, and local row deletion.
- **Activity** and **Income** use the local activity ledger.
- **Analytics** covers deterministic diversification plus explicit missing states
  for adjusted-return performance, historical risk, and ETF look-through.
- **Alerts** (Decisions) keeps your decision, thesis, conviction, and review
  triggers separate from any non-binding Claude suggestion, and lists exit-plan
  proposals waiting for review.
- **AI review packs** export a privacy-controlled Markdown pack and import a Claude
  response manually.
- **Settings** shows the data source, quote provider, history, prompts, the demo
  loader, and the local data-deletion control.

Historical analytics are descriptive, not forecasts, and missing evidence is never
replaced with a fabricated value.

## Exit plans

An exit plan is a target price, a stop price, and/or a review date, with the
reasoning behind them.

- **Claude's plans arrive as proposals**, labeled "Proposed by Claude". A new
  proposal replaces Claude's earlier open proposal for the same ticker.
- **A proposal changes nothing until you accept it** on the Research screen.
  Accepting creates review-only triggers (above the target, below the stop, on the
  review date), saves the reasoning as a dated note, and records the acceptance in
  decision history. Your decision itself is not changed.
- **Only one accepted plan per ticker.** Accepting a new plan retires the previous
  one and dismisses its triggers. Rejected plans stay in the history.
- **Plans you write yourself** are accepted as soon as you save them.
- **Alerts quote the reasoning.** Triggers are checked against the cached daily
  close, so watchlist tickers are covered too. When a level is crossed or the
  review date arrives, the alert shows the original reasoning. Alerts are reminders
  to review; they never create orders.

## Claude Desktop (MCP server)

`backend/app/mcp_server.py` is a local [Model Context Protocol](https://modelcontextprotocol.io)
server for Claude Desktop (it works with a Claude Pro plan). It runs over stdio on
this computer and uses the same database and services as the dashboard.

- **Read tools:** `get_quote`, `get_chart_summary`, `get_fundamentals`, `get_peers`,
  `get_insider_activity`, `get_news_sentiment`, `get_macro_snapshot`, `get_my_notes`, `get_watchlist`, `get_position`. Every
  response carries as-of dates, and missing values read `NOT AVAILABLE` instead of
  being left blank.
- **Write tools:** `add_note`, `add_to_watchlist`, and `save_exit_plan`. The last
  one only ever saves a proposal.
- **Prompt:** "Full stock analysis" takes a ticker. Its text lives in
  `backend/app/prompts/full_stock_analysis.md`; replace it with your own.

The **MCP Server** button in the app's header opens these steps with this
computer's paths already filled in, checks that Python and the `mcp` package are
installed, and has a Copy button for the configuration.

To connect it:

1. Install the project (see Development setup), which installs the `mcp` package.
2. Open Claude Desktop → Settings → Developer → Edit Config, and add the server from
   [`docs/claude_desktop_config.json`](docs/claude_desktop_config.json), replacing
   `/ABSOLUTE/PATH/TO/Portfolio-Manager` with this folder's path.
3. Restart Claude Desktop. "investment-tracker" appears in the tools menu, and
   "Full stock analysis" in the prompts list.

The server reads the same data folder as the app (`~/.portfolio-manager` unless
`PORTFOLIO_MANAGER_HOME` is set). If the project lives in Desktop or Documents,
macOS may ask to give Claude access to that folder. Logs go to Claude Desktop's MCP
log, never to stdout.

## Daily check

`./scripts/check` refreshes daily prices for every ticker with an open review
trigger (and the portfolio valuation), checks the triggers, and shows a macOS
notification for each due alert with the level and the exit plan's reasoning.

- Each alert is notified once, including alerts the dashboard already found. If a
  notification fails, the next run tries it again.
- `./scripts/check --no-notify` prints what is due without notifying or marking
  anything as sent; `--json` prints the full result.
- A ticker whose prices can't be refreshed is reported, and its saved close is
  used, marked stale (stale closes never fire price triggers).
- Run it after the US close. There is no automatic schedule yet.

## Sector allocation

- Direct stocks use a locally editable sector dropdown. The application never
  guesses an unclassified stock; its value remains visible as `Unknown`.
- Cash is classified as cash.
- ETFs use aggregate sector weights from issuer product pages or factsheets.
  Verified issuer profiles live in `backend/app/data/etf_sector_profiles.json`;
  an ETF without a profile remains `Unknown` until one is added with its source
  link, data as-of date, and verification date.
- Evidence older than 120 days is clearly marked stale.

## Requirements

- macOS with Python 3.11 or newer
- Node.js 20 or newer

## Development setup

```bash
./scripts/bootstrap
./scripts/dev
```

Then open `http://127.0.0.1:5173`.

Headline sentiment needs FinBERT, which is optional because PyTorch is large:

```bash
.venv/bin/pip install -e ".[sentiment]"
```

The model (about 440 MB) downloads on first use and is cached. Without it, headlines
still show and sentiment reads "not available".

To run all tests and the production frontend build:

```bash
./scripts/test
```

## FRED setup

Macro data and the release calendar come from FRED, which needs a free API key.
Request one at fredaccount.stlouisfed.org (API Keys) and add it to `.env`:

```bash
FRED_API_KEY=your_key
```

Restart `./scripts/dev` after adding it. Without a key, the Macro drawer still
shows world news and Fed meeting dates. Series are cached for 6 hours and release
dates for 12, and a saved copy is shown, marked stale, if FRED can't be reached.
The key never appears in error messages.

## SEC EDGAR setup

SEC asks automated clients to identify themselves. Fundamentals, insider activity,
and peers stay unavailable until you set a name and contact email, either in your
shell or in a local `.env` file (ignored by Git), which `./scripts/dev` loads:

```bash
PORTFOLIO_MANAGER_SEC_USER_AGENT="Jane Doe jane@example.com"
```

Requests are limited to under 10 per second as SEC requires. Company facts and
filings are cached in SQLite (facts for 24 hours, filing lists for 12 hours, parsed
Form 4 filings permanently), and an expired copy is shown, marked stale, if SEC
can't be reached.

## Local data controls

- **Delete local data** removes holdings snapshots, valuations, quotes, and
  activities after confirmation. Decisions, theses, triggers, prompts, and AI
  reviews are kept.
- Row deletion creates a new local snapshot without the selected row. It is never
  an order.

## Environment overrides

```bash
# Default: ~/.portfolio-manager
PORTFOLIO_MANAGER_HOME=/path/to/private/runtime

# Default: 127.0.0.1
PORTFOLIO_MANAGER_HOST=127.0.0.1

# Default: 8742
PORTFOLIO_MANAGER_PORT=8742
```
