# SnapTrade read-only security design and audit

Audit date: 2026-09-11

Status: **PASS for synthetic development.** The adapter remains disabled by
default and no real SnapTrade or Wealthsimple connection was made during the audit.

## Security design

Investment Tracker uses SnapTrade's Personal API Key model. Signed requests contain
the Personal client ID, timestamp, and signature, and deliberately omit commercial
`userId` and `userSecret` parameters. The Connection Portal payload always requests
`connectionType: "read"`. It deliberately omits the optional broker filter because
SnapTrade does not document a stable Wealthsimple broker slug; select Wealthsimple
inside SnapTrade's hosted portal. The application subsequently ignores every
non-Wealthsimple connection and rejects any Wealthsimple connection that is not
reported as read-only.

The integration is a small custom client rather than the general-purpose SnapTrade
SDK. Its transport rejects every method/path pair except this exact allowlist:

| Method | SnapTrade API path | Purpose |
| --- | --- | --- |
| `POST` | `/snapTrade/login` | Create read-only Connection Portal URL |
| `GET` | `/authorizations` | Inspect connection type and status |
| `GET` | `/accounts` | List accounts after permission validation |
| `GET` | `/accounts/{uuid}/positions/all` | Read positions |
| `GET` | `/accounts/{uuid}/balances` | Read currency balances |
| `GET` | `/accounts/{uuid}/activities` | Read completed activities (daily/cached) |
| `DELETE` | `/connection/{uuid}` | Disconnect the brokerage |

No wildcard suffixes or arbitrary request helper is exposed as a public operation.
Account and connection UUIDs are accepted only in UUID-shaped path segments.

## Secret handling

- Service: `com.portfolio-manager.snaptrade`
- Keychain account for the client ID: `client-id`
- Keychain account for the consumer key: `consumer-key`
- Credentials are fetched at request time with the macOS `security` executable.
- Credential objects redact their representation.
- The app has no endpoint, form, command-line parameter, `.env` variable, or
  configuration property for entering either value.
- SnapTrade response bodies and outbound URLs are never included in user-facing
  errors. Only a redacted operation name, HTTP status, and a strictly validated
  non-sensitive request/correlation ID may be shown.
- SQLite stores immutable holdings, local aliases, hashes, sync timestamps, and
  warnings. It stores neither key nor raw SnapTrade/Wealthsimple account IDs.

The random `local-secret.key` under the private runtime directory is not a SnapTrade
credential. It exists only to HMAC account UUIDs into stable local aliases.

## Synchronization and data controls

- A non-`read` Wealthsimple connection is rejected before account or holdings calls.
- Disabled connections are surfaced and are not synchronized.
- At most one synchronization attempt is allowed every ten minutes.
- Every synchronization creates a local preview first. Applying requires an exact
  confirmation token and creates an immutable snapshot.
- Completed activities use UUID-only account paths, ISO date filters, a maximum
  page size of 1,000, and bounded pagination. They are fetched no more than once
  every 24 hours. The preview reports additions, changed normalized records, type
  counts, missing symbols, unsupported types, date coverage, and incomplete history.
- Only normalized activity fields are retained. External identifiers are HMAC-hashed
  for local deduplication; raw account IDs and raw payloads are not stored.
- SnapTrade-supplied market prices are discarded. The independent market-price
  provider supplies dated quotes used for local valuation.
- Disconnect is explicit and confirmed. Local brokerage-data deletion is a separate,
  explicit confirmation and preserves historical legacy CSV snapshots.

## Audit evidence

The automated suite verifies:

- the portal body requests `read` and contains no `userId`/`userSecret`;
- every allowed path is signed and contains no consumer key;
- representative trade, order, cancellation, mutation, and unknown paths are
  rejected before the network transport is reached;
- completed activities are the only added account-data endpoint; their parameters,
  pagination, normalization, deduplication, and incomplete coverage are tested;
- a trade-enabled connection is rejected before accounts are read;
- the application exposes no order or trading API route;
- synchronization cannot be applied without explicit confirmation;
- raw account and connection IDs do not appear in API previews or SQLite;
- non-destructive schema migrations preserve existing holdings byte-for-byte and
  pass foreign-key checks;
- deleting local SnapTrade data follows derived snapshot lineage, preserves legacy
  snapshots, and does not delete independent quote or instrument evidence;
- the dashboard never auto-applies an app-open synchronization preview.

Static inspection also confirms that there is no order model, order client method,
brokerage trade route, or trading UI in the application. The eight application tabs
display `No order actions available` where brokerage activity is shown. Tests use
only synthetic responses and an in-memory HTTP transport.

## Manual Keychain setup (only after this audit passes)

Do this yourself in the macOS **Keychain Access** graphical application. Do not send
either value to Codex and do not paste either value into Terminal.

1. Open **Applications → Utilities → Keychain Access**.
2. Select the `login` keychain, then choose **File → New Password Item**.
3. Create the first item with **Keychain Item Name**
   `com.portfolio-manager.snaptrade`, **Account Name** `client-id`, and put the real
   SnapTrade client ID in the password field.
4. Create a second item with the same **Keychain Item Name** and **Account Name**
   `consumer-key`; put the real SnapTrade consumer key in the password field.
5. Close Keychain Access. Do not export these items.
6. Start the app with the non-secret feature flag:

   ```bash
   PORTFOLIO_MANAGER_SNAPTRADE_ENABLED=1 ./scripts/dev
   ```

7. Click **Connect**, then select Wealthsimple in SnapTrade's portal. Enter
   Wealthsimple credentials and MFA only in that HTTPS SnapTrade portal. Return to
   Investment Tracker, inspect the preview, and apply it only if every change is
   correct.

macOS may ask whether the local Python process may access those Keychain items. Read
the prompt carefully and allow access only while using this local application.

## Evidence basis

- [SnapTrade authentication methods](https://docs.snaptrade.com/docs/authentication-methods)
- [Connection Portal endpoint](https://docs.snaptrade.com/reference/Authentication/Authentication_loginSnapTradeUser)
- [Connection status and permission](https://docs.snaptrade.com/reference/Connections/Connections_listBrokerageAuthorizations)
- [Account positions](https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAllAccountPositions)
- [Account balances](https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getUserAccountBalance)
- [Completed account activities](https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities)
- [Request signatures](https://docs.snaptrade.com/docs/request-signatures)
- [Disconnect semantics](https://docs.snaptrade.com/reference/Connections/Connections_deleteConnection)
