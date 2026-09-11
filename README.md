# Portfolio Manager

A standalone, local-first, read-only portfolio dashboard for a Canadian retail
investor. Wealthsimple holdings are synchronized through SnapTrade's Connection
Portal and must be reviewed before they become a new immutable local snapshot.

The SnapTrade adapter is disabled by default. Development and tests use synthetic
responses only. The application has no order, trading, or brokerage-credential UI.

## Safety boundary

- SnapTrade Personal API Key authentication; no SnapTrade user registration and no
  `userId` or `userSecret`.
- The Connection Portal request always uses `connectionType="read"`. Select
  Wealthsimple inside SnapTrade's hosted portal. The application ignores other
  brokerages, and a Wealthsimple connection reported as anything other than `read`
  is rejected before accounts or holdings are requested.
- The outbound client has an exact, deny-by-default endpoint allowlist for portal
  creation, connection status, accounts, positions, balances, and disconnection.
- No order placement, modification, cancellation, order-history, trading routes,
  or trading UI.
- Wealthsimple credentials and MFA are entered only in SnapTrade's hosted portal.
- SnapTrade client ID and consumer key are read only from macOS Keychain. There are
  no secret input fields, secret environment variables, or SQLite secret columns.
- No Claude or other AI API integration.
- Runtime data is stored under `~/.canadian-portfolio-manager/` by default with
  restrictive local permissions.

See [SnapTrade security design and audit](docs/SNAPTRADE_SECURITY.md).

## Synchronization workflow

1. When enabled, the app checks for an eligible read-only connection and prepares
   a holdings preview once when the app opens. A manual **Sync** button does the same.
2. The backend enforces a minimum ten-minute interval between synchronization
   attempts. It reports connection status, last successful sync, holdings `as_of`,
   disabled connections, and stale data.
3. The preview lists additions, removals, quantity changes, cost-basis changes,
   cash changes, and unresolved symbols. Ambiguous exchanges are not guessed.
4. Nothing changes until the review checkbox is selected and **Apply snapshot** is
   clicked. Accepted data becomes a new immutable `snaptrade_read_sync` snapshot.
5. SnapTrade position prices are ignored. Market quotes are retrieved separately,
   timestamped, classified as real-time/delayed/end-of-day/stale, and used to
   calculate CAD portfolio values locally.

After returning from SnapTrade's portal, the application verifies the connection
before offering another Connect action. Disconnect is asynchronous: use **Check
Status** until the state becomes **Not Connected**, then open exactly one new portal
session. When already connected, use **Sync**, not **Connect**.

The current Yahoo daily price adapter does not promise a safe 30–60 second refresh
interval, so automatic quote polling remains off. A future provider can opt in only
with a declared interval between 30 and 60 seconds.

Legacy CSV snapshots remain readable after the non-destructive database migration,
but CSV upload routes and the CSV import UI are inactive.

## Sector allocation

- Direct stocks use a locally editable sector dropdown. The application never
  guesses an unclassified stock; its value remains visible as `Unknown`.
- Cash is classified as cash.
- ETFs use aggregate sector weights from issuer product pages or factsheets,
  not only their top holdings. The dashboard shows the source link, data as-of
  date, verification date, coverage, and stale status.
- Holdings-table columns can be shown or hidden from the Columns menu. Account,
  Exchange, and Currency are hidden by default; preferences are kept locally in
  the browser.
- Select a holding from its row number, then press Delete/Backspace or use Delete
  Row. This creates a new local portfolio snapshot without that row; it never
  represents a trade.
- The initial issuer evidence set supports AIQ, VEQT, and ZEM. An unsupported
  ETF remains `Unknown` until a verified profile is added.
- Issuer weights are normalized only for small rounding differences. Vanguard
  ICB labels such as Technology, Basic Materials, and Telecommunications are
  mapped to the common labels used by the dashboard.
- Evidence older than 120 days is clearly marked stale. It is not silently
  replaced by an unrelated or undated source.

Public issuer profiles live in
`backend/app/data/etf_sector_profiles.json`. This file contains no portfolio
quantities, account data, or other personal information.

## Requirements

- macOS with Python 3.11 or newer
- Node.js 20 or newer

## Development setup

```bash
./scripts/bootstrap
./scripts/dev
```

Then open `http://127.0.0.1:5173`.

This starts with SnapTrade disabled. Do not add real credentials during development
or testing.

To run all tests and the production frontend build:

```bash
./scripts/test
```

## Local data controls

- **Disconnect** asks SnapTrade to remove the Wealthsimple connection. SnapTrade
  processes that operation asynchronously; local historical snapshots remain.
- **Delete local brokerage data** removes SnapTrade-derived snapshots, previews,
  aliases, and synchronization metadata after confirmation. Historical legacy CSV
  snapshots remain.
- Spreadsheet row deletion still creates a new local snapshot without the selected
  row. It does not act at Wealthsimple and is never an order.

## Environment overrides

```bash
# Default: ~/.canadian-portfolio-manager
PORTFOLIO_MANAGER_HOME=/path/to/private/runtime

# Default: 127.0.0.1
PORTFOLIO_MANAGER_HOST=127.0.0.1

# Default: 8742
PORTFOLIO_MANAGER_PORT=8742

# Default: 0 (disabled). Enable only after completing the Keychain steps in
# docs/SNAPTRADE_SECURITY.md.
PORTFOLIO_MANAGER_SNAPTRADE_ENABLED=0
```

SnapTrade client ID and consumer key deliberately have no environment variables.
Do not put them in `.env`, shell history, source files, SQLite, logs, or issue text.
