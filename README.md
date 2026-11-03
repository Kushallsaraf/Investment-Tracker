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
- No Claude or other AI API integration. Research packs leave the application only
  when you copy or export them.
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

The fixed dark interface has two top-level tabs.

**Terminal** is a single-ticker research screen. Open any US stock or ETF from the
ticker search (`⌘K`, `Ctrl K`, or `/`) or the watchlist.

- A market strip shows SPY, QQQ, DIA, IWM, VIX, the 10-year yield, the dollar
  index, oil, gold, and bitcoin from daily data.
- The chart uses TradingView Lightweight Charts with candle/line views, 1M–MAX
  ranges, EMA 20/50, SMA 200, and Bollinger overlays, volume, and an RSI or MACD
  pane. Daily history is cached in SQLite and refreshed at most every 15 minutes.
- Technical setup describes trend, RSI, MACD, 52-week range position, 3-month
  strength against SPY, ATR, a 2× ATR stop level, and relative volume. Every
  indicator is calculated in Python; nothing is a signal or forecast.
- Fundamentals come from SEC EDGAR company facts (10-K and 10-Q): market cap,
  P/E, P/S, EV/EBITDA, free-cash-flow yield, growth, margins, net cash, and P/E and
  P/S compared with the company's own five-year range. Trailing-twelve-month values
  are built from quarterly filings, deriving quarters from year-to-date figures where
  needed. ETFs show "not applicable" because they don't file company financials.
- Insider activity reads Form 4 filings from the last 90 days. Open-market buys and
  sales are totaled; grants, exercises, and tax withholding are listed but excluded,
  and pre-planned 10b5-1 sales are marked.
- Peers are seeded from the company's SEC industry code (larger companies first) and
  can be edited or reset. The table compares valuation, growth, margins, and
  3-month return.
- Notes are saved per ticker and can be pinned to a date; pinned notes appear as
  markers on the chart (click a candle to pick its date). The notes panel also
  records your decision for any ticker, held or not, and lists its open review
  triggers. Price triggers on tickers you don't hold are checked against the cached
  daily close.
- The AI analyst, strategy scanner, news and sentiment, and macro panels are
  placeholders until their data sources are connected.

**Portfolio** keeps the holdings workspace in eight sub-views:

- **Overview** shows portfolio totals, data warnings, sector allocation, and the
  largest holdings. Unsupported return and income figures remain unavailable.
- **Holdings** is an Excel-style worksheet with an add/update form, saved column
  preferences, editable stock sectors and decisions, and local row deletion.
- **Analytics** covers deterministic diversification plus explicit missing states
  for adjusted-return performance, historical risk against the S&P 500 Total
  Return Index, and issuer-verified ETF look-through.
- **Income** and **Activity** use the local activity ledger.
- **Decisions** keeps the investor's decision, thesis, conviction, and review
  triggers separate from any non-binding Claude suggestion.
- **Research** exports a privacy-controlled Markdown review pack and imports a
  Claude response manually. It never calls Claude.
- **Settings** shows the portfolio data source, quote provider, immutable history,
  local prompts, the demo loader, and the local data-deletion control.

Historical analytics are descriptive, not forecasts, and missing evidence is never
replaced with a fabricated value.

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

To run all tests and the production frontend build:

```bash
./scripts/test
```

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
