import { useEffect, useMemo, useRef, useState } from "react";
import {
  applySnapTradeSync,
  cancelSnapTradeSync,
  createSnapTradePortal,
  deleteLocalBrokerageData,
  disconnectSnapTrade,
  getHistory,
  getPendingSnapTradeSync,
  getPortfolio,
  getPriceCapabilities,
  getSectorAnalysis,
  getSnapTradeStatus,
  previewSnapTradeSync,
  refreshPrices,
  removePortfolioPosition,
  updateInstrumentSector,
} from "./api";
import type {
  HistoryPoint,
  Holding,
  Portfolio,
  PriceCapabilities,
  SectorAnalysis,
  SectorCategory,
  SectorName,
  SnapTradeStatus,
  SnapTradeSyncPreview,
} from "./types";

const SECTOR_COLORS: Record<string, string> = {
  "Information Technology": "#49a7ff",
  Financials: "#65d6a5",
  Industrials: "#ffc857",
  "Consumer Discretionary": "#ff8f70",
  Energy: "#a78bfa",
  Materials: "#d6a75f",
  "Health Care": "#e879f9",
  "Communication Services": "#67e8f9",
  "Consumer Staples": "#86d16f",
  Utilities: "#f472b6",
  "Real Estate": "#94a3b8",
  Cash: "#b6c2cf",
  Other: "#6b7280",
  Unknown: "#343b44",
};

type ColumnKey =
  | "symbol"
  | "name"
  | "account"
  | "type"
  | "exchange"
  | "currency"
  | "sector"
  | "quantity"
  | "averageCost"
  | "lastPrice"
  | "marketValue"
  | "gainLoss"
  | "weight"
  | "priceStatus"
  | "priceAsOf"
  | "source";

const COLUMN_OPTIONS: { key: ColumnKey; label: string }[] = [
  { key: "symbol", label: "Symbol" },
  { key: "name", label: "Security name" },
  { key: "account", label: "Account" },
  { key: "type", label: "Type" },
  { key: "exchange", label: "Exchange" },
  { key: "currency", label: "Currency" },
  { key: "sector", label: "Sector" },
  { key: "quantity", label: "Quantity" },
  { key: "averageCost", label: "Avg cost" },
  { key: "lastPrice", label: "Last price" },
  { key: "marketValue", label: "Market value" },
  { key: "gainLoss", label: "Gain / loss" },
  { key: "weight", label: "Weight" },
  { key: "priceStatus", label: "Price status" },
  { key: "priceAsOf", label: "Price as of" },
  { key: "source", label: "Source" },
];

const DEFAULT_COLUMNS: ColumnKey[] = [
  "symbol",
  "name",
  "type",
  "sector",
  "quantity",
  "averageCost",
  "lastPrice",
  "marketValue",
  "gainLoss",
  "weight",
  "priceStatus",
  "priceAsOf",
  "source",
];
const COLUMN_STORAGE_KEY = "portfolio-manager.visible-columns.v1";

function initialColumns(): ColumnKey[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem(COLUMN_STORAGE_KEY) ?? "null");
    if (Array.isArray(saved)) {
      const allowed = new Set(COLUMN_OPTIONS.map((column) => column.key));
      const selected = saved.filter((key): key is ColumnKey => allowed.has(key));
      if (!selected.includes("symbol")) selected.unshift("symbol");
      return COLUMN_OPTIONS.map((column) => column.key).filter((key) => selected.includes(key));
    }
  } catch {
    // A damaged preference is harmless; restore the defaults.
  }
  return DEFAULT_COLUMNS;
}

function cad(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function number(value: string | null): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 6 }).format(Number(value));
}

function percent(value: string | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

function timestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("en-CA") : "—";
}

function evidenceStatus(row: Holding): { label: string; className: string } {
  if (!row.price) return { label: "MISSING", className: "status-bad" };
  if (row.price_stale || row.data_status.includes("stale")) {
    return {
      label: row.quote_status === "imported" ? "STALE / IMPORTED" : "STALE",
      className: "status-warn",
    };
  }
  return { label: (row.quote_status ?? "AVAILABLE").toUpperCase(), className: "status-good" };
}

function valueWithCurrency(value: string | null, currency: string | null): string {
  const formatted = number(value);
  if (formatted === "—" || !currency || currency === "CAD") return formatted;
  return `${formatted} ${currency}`;
}

export function App() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [sectors, setSectors] = useState<SectorAnalysis | null>(null);
  const [snaptradeStatus, setSnaptradeStatus] = useState<SnapTradeStatus | null>(null);
  const [priceCapabilities, setPriceCapabilities] = useState<PriceCapabilities | null>(null);
  const [syncPreview, setSyncPreview] = useState<SnapTradeSyncPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [snaptradeBusy, setSnaptradeBusy] = useState(false);
  const [sectorBusy, setSectorBusy] = useState<string | null>(null);
  const [rowBusy, setRowBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmSync, setConfirmSync] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(initialColumns);
  const automaticSyncAttempted = useRef(false);

  async function load() {
    const [current, points, analysis, connection, priceSupport, pendingPreview] = await Promise.all([
      getPortfolio(),
      getHistory(),
      getSectorAnalysis(),
      getSnapTradeStatus(),
      getPriceCapabilities(),
      getPendingSnapTradeSync(),
    ]);
    setPortfolio(current);
    setHistory(points);
    setSectors(analysis);
    setSnaptradeStatus(connection);
    setPriceCapabilities(priceSupport);
    setSyncPreview(pendingPreview);
    setConfirmSync(false);
    setSelectedPositionId(null);
  }

  useEffect(() => {
    void load().catch((cause) =>
      setError(cause instanceof Error ? cause.message : "Unable to load portfolio"),
    );
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibleColumns));
  }, [visibleColumns]);

  async function startSnapTradeSync(automatic = false) {
    if (snaptradeBusy || syncPreview) return;
    setSnaptradeBusy(true);
    if (!automatic) {
      setError(null);
      setNotice(null);
    }
    try {
      const preview = await previewSnapTradeSync();
      setSyncPreview(preview);
      setConfirmSync(false);
    } catch (cause) {
      if (!automatic) {
        setError(cause instanceof Error ? cause.message : "Unable to synchronize Wealthsimple");
      }
    } finally {
      setSnaptradeBusy(false);
      await getSnapTradeStatus().then(setSnaptradeStatus).catch(() => undefined);
    }
  }

  useEffect(() => {
    if (
      automaticSyncAttempted.current
      || !snaptradeStatus?.adapter_enabled
      || !snaptradeStatus.sync_allowed
    ) return;
    automaticSyncAttempted.current = true;
    void startSnapTradeSync(true);
  }, [snaptradeStatus]);

  useEffect(() => {
    const seconds = priceCapabilities?.automatic_refresh_seconds;
    if (
      !priceCapabilities?.automatic_refresh_supported
      || seconds == null
      || seconds < 30
      || seconds > 60
      || !portfolio
    ) return;
    const timer = window.setInterval(() => {
      void refreshPrices().then(load).catch(() => undefined);
    }, seconds * 1000);
    return () => window.clearInterval(timer);
  }, [priceCapabilities, portfolio?.holding_snapshot_id]);

  async function openSnapTradePortal() {
    setSnaptradeBusy(true);
    setError(null);
    setNotice(null);
    try {
      const redirect = await createSnapTradePortal();
      window.location.assign(redirect);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open SnapTrade");
      setSnaptradeBusy(false);
    }
  }

  async function applySync() {
    if (!syncPreview || !confirmSync) return;
    setSnaptradeBusy(true);
    setError(null);
    try {
      await applySnapTradeSync(syncPreview.preview_id);
      setSyncPreview(null);
      setConfirmSync(false);
      await load();
      setNotice("The reviewed Wealthsimple holdings were saved as a new portfolio snapshot.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to apply synchronization");
    } finally {
      setSnaptradeBusy(false);
    }
  }

  async function cancelSync() {
    if (syncPreview) await cancelSnapTradeSync(syncPreview.preview_id).catch(() => undefined);
    setSyncPreview(null);
    setConfirmSync(false);
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Wealthsimple from SnapTrade? This stops future synchronization but does not delete local snapshots.")) return;
    setSnaptradeBusy(true);
    setError(null);
    try {
      await disconnectSnapTrade();
      await load();
      setNotice("Wealthsimple disconnection was requested. SnapTrade may finish it asynchronously.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to disconnect Wealthsimple");
    } finally {
      setSnaptradeBusy(false);
    }
  }

  async function deleteBrokerageData() {
    if (!window.confirm("Delete every local snapshot created from SnapTrade? Existing legacy CSV snapshots will be preserved. This cannot be undone.")) return;
    setSnaptradeBusy(true);
    setError(null);
    try {
      await deleteLocalBrokerageData();
      setSyncPreview(null);
      await load();
      setNotice("Local SnapTrade snapshots and synchronization metadata were deleted.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete local brokerage data");
    } finally {
      setSnaptradeBusy(false);
    }
  }

  async function refresh() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await refreshPrices();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Price refresh failed");
    } finally {
      setBusy(false);
    }
  }

  async function changeSector(instrumentId: string, value: string) {
    setSectorBusy(instrumentId);
    setError(null);
    setNotice(null);
    try {
      await updateInstrumentSector(instrumentId, (value || null) as SectorName | null);
      const [current, analysis] = await Promise.all([getPortfolio(), getSectorAnalysis()]);
      setPortfolio(current);
      setSectors(analysis);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update sector");
    } finally {
      setSectorBusy(null);
    }
  }

  async function removeSelectedRow() {
    const row = portfolio?.holdings.find((holding) => holding.position_id === selectedPositionId);
    if (!row || rowBusy) return;
    setRowBusy(true);
    setError(null);
    setNotice(null);
    try {
      await removePortfolioPosition(row.position_id);
      await load();
      setNotice(`${row.canonical_symbol} was removed from the current portfolio snapshot. No trade was placed.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to remove holding row");
    } finally {
      setRowBusy(false);
    }
  }

  useEffect(() => {
    function handleDeleteKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing = target?.isContentEditable
        || target?.tagName === "INPUT"
        || target?.tagName === "SELECT"
        || target?.tagName === "TEXTAREA";
      if (editing || event.repeat || !selectedPositionId || rowBusy) return;
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        void removeSelectedRow();
      }
    }
    window.addEventListener("keydown", handleDeleteKey);
    return () => window.removeEventListener("keydown", handleDeleteKey);
  }, [portfolio, rowBusy, selectedPositionId]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (portfolio?.holdings ?? []).filter(
      (row) =>
        (!needle || `${row.canonical_symbol} ${row.security_name}`.toLowerCase().includes(needle)),
    );
  }, [portfolio, query]);

  function toggleColumn(key: ColumnKey) {
    if (key === "symbol") return;
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return COLUMN_OPTIONS.map((column) => column.key).filter((column) => next.has(column));
    });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark">PM</span>
          <div>
            <h1>Portfolio Manager</h1>
            <span className="workspace-label">CANADIAN PORTFOLIO / CAD</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="read-only">LOCAL · READ-ONLY</span>
          <button
            className="button"
            disabled={!snaptradeStatus?.adapter_enabled || !snaptradeStatus.sync_allowed || snaptradeBusy || Boolean(syncPreview)}
            onClick={() => void startSnapTradeSync()}
          >
            {snaptradeBusy ? "SYNCING…" : "SYNC WEALTHSIMPLE"}
          </button>
          <button className="button primary" disabled={!portfolio || busy} onClick={() => void refresh()}>
            {busy ? "WORKING…" : "REFRESH PRICES"}
          </button>
        </div>
      </header>

      <div className="tabbar">
        <span className="tab active">PORTFOLIO</span>
        <span className="tab-note">Read-only holdings connection · no order capability</span>
      </div>

      {error && <div className="error-line" role="alert">ERROR: {error}</div>}
      {notice && <div className="notice-line" role="status">{notice}</div>}

      <SnapTradeConnectionPanel
        status={snaptradeStatus}
        priceCapabilities={priceCapabilities}
        busy={snaptradeBusy}
        previewOpen={Boolean(syncPreview)}
        onConnect={() => void openSnapTradePortal()}
        onSync={() => void startSnapTradeSync()}
        onDisconnect={() => void disconnect()}
        onDeleteLocalData={() => void deleteBrokerageData()}
      />

      {syncPreview && (
        <SnapTradePreviewPanel
          preview={syncPreview}
          busy={snaptradeBusy}
          confirmed={confirmSync}
          setConfirmed={setConfirmSync}
          onApply={() => void applySync()}
          onCancel={() => void cancelSync()}
        />
      )}

      {portfolio ? (
        <>
          <section className="summary-strip" aria-label="Portfolio summary">
            <SummaryCell label="PORTFOLIO VALUE" value={cad(portfolio.total_cad)} detail="Known CAD value" />
            <SummaryCell label="PRICE COVERAGE" value={percent(portfolio.position_coverage_pct)} detail={`${portfolio.priced_positions}/${portfolio.total_positions} positions`} />
            <SummaryCell label="SECTOR COVERAGE" value={percent(sectors?.coverage_pct)} detail="Known portfolio value" />
            <SummaryCell label="VALUATION AS OF" value={timestamp(portfolio.created_at)} detail="Frozen snapshot" />
            <SummaryCell label="USD/CAD" value={portfolio.fx?.rate ?? "N/A"} detail={portfolio.fx ? timestamp(portfolio.fx.observed_at) : "No USD holdings"} />
          </section>

          <section className="analysis-grid">
            <article className="sheet sector-sheet">
              <SectionHeader title="SECTOR ALLOCATION" meta={`Includes sectors inside ETFs · ${percent(sectors?.coverage_pct)} covered`} />
              {sectors ? <SectorView analysis={sectors} /> : <div className="empty-cell">Sector analysis unavailable.</div>}
            </article>

            <div className="side-stack">
              <article className="sheet history-sheet">
                <SectionHeader title="SNAPSHOT HISTORY" meta={`${history.length} valuation${history.length === 1 ? "" : "s"}`} />
                <div className="history-body"><HistoryChart points={history} /></div>
              </article>
              <article className="sheet quality-sheet">
                <SectionHeader title="DATA QUALITY" meta={`${portfolio.warnings.length + (sectors?.warnings.length ?? 0)} notices`} />
                <DataQuality warnings={[...portfolio.warnings, ...(sectors?.warnings ?? [])]} />
              </article>
            </div>
          </section>

          {sectors && sectors.evidence.length > 0 && <EtfEvidence analysis={sectors} />}

          <section className="sheet holdings-sheet">
            <div className="sheet-toolbar">
              <div><strong>HOLDINGS</strong><span>Snapshot {timestamp(portfolio.created_at)}</span></div>
              <div className="filters">
                <input aria-label="Search holdings" placeholder="Find symbol or name" value={query} onChange={(event) => setQuery(event.target.value)} />
                <button
                  className="button danger"
                  type="button"
                  disabled={!selectedPositionId || rowBusy || busy}
                  onClick={() => void removeSelectedRow()}
                >
                  {rowBusy ? "REMOVING…" : "DELETE ROW"}
                </button>
                <ColumnChooser
                  visibleColumns={visibleColumns}
                  onToggle={toggleColumn}
                  onReset={() => setVisibleColumns(DEFAULT_COLUMNS)}
                />
              </div>
            </div>
            <div className="table-scroll holdings-scroll">
              <table className="grid-table holdings-table" style={{ minWidth: Math.max(860, visibleColumns.length * 116 + 40) }}>
                <thead>
                  <tr className="column-letters"><th />{visibleColumns.map((column, index) => <th key={column}>{String.fromCharCode(65 + index)}</th>)}</tr>
                  <tr><th>#</th>{visibleColumns.map((column) => <th className={`column-${column}`} key={column}>{COLUMN_OPTIONS.find((option) => option.key === column)?.label}</th>)}</tr>
                </thead>
                <tbody>
                  {filtered.map((row, index) => (
                    <HoldingRow
                      key={row.position_id}
                      row={row}
                      index={index + 1}
                      sectorOptions={sectors?.sector_options ?? []}
                      visibleColumns={visibleColumns}
                      selected={selectedPositionId === row.position_id}
                      sectorBusy={sectorBusy === row.instrument_id}
                      onSelect={() => setSelectedPositionId((current) => current === row.position_id ? null : row.position_id)}
                      onSector={(value) => void changeSector(row.instrument_id, value)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="price-status-guide"><strong>PRICE STATUS</strong><span>END OF DAY = last market close.</span><span>STALE = refresh did not return a newer quote, so an older or imported price is being used. Check Price as of and Source.</span><span>MISSING = no usable price.</span></div>
            <div className="sheet-statusbar">
              {selectedPositionId
                ? "1 row selected · Press Delete/Backspace or choose Delete Row."
                : "Click a row number to select a holding."}
              {` · ${filtered.length} visible rows · Research inputs, never orders.`}
            </div>
          </section>
        </>
      ) : (
        <section className="sheet empty-state">
          <div className="empty-title">NO PORTFOLIO LOADED</div>
          <p>Connect Wealthsimple through SnapTrade's read-only portal, preview the synchronized holdings, and approve the first snapshot.</p>
          <button className="button primary" disabled={!snaptradeStatus?.adapter_enabled || snaptradeBusy} onClick={() => void openSnapTradePortal()}>CONNECT WEALTHSIMPLE</button>
        </section>
      )}

      <footer>No orders · Read-only SnapTrade connection · No AI API · Research only · Secrets stay in macOS Keychain</footer>
    </main>
  );
}

function SummaryCell({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="summary-cell"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function SectionHeader({ title, meta }: { title: string; meta: string }) {
  return <div className="section-header"><strong>{title}</strong><span>{meta}</span></div>;
}

function connectionLabel(status: SnapTradeStatus | null): string {
  if (!status) return "CHECKING";
  const labels: Record<string, string> = {
    adapter_disabled: "ADAPTER DISABLED",
    not_checked: "NOT CHECKED",
    credentials_missing: "KEYCHAIN SETUP REQUIRED",
    not_connected: "NOT CONNECTED",
    connected_read_only: "CONNECTED · READ ONLY",
    disabled_connection: "CONNECTION DISABLED",
    rejected_trade_enabled: "CONNECTION REJECTED",
    disconnect_pending: "DISCONNECTING",
  };
  return labels[status.connection_status] ?? status.connection_status.replaceAll("_", " ").toUpperCase();
}

function SnapTradeConnectionPanel({
  status,
  priceCapabilities,
  busy,
  previewOpen,
  onConnect,
  onSync,
  onDisconnect,
  onDeleteLocalData,
}: {
  status: SnapTradeStatus | null;
  priceCapabilities: PriceCapabilities | null;
  busy: boolean;
  previewOpen: boolean;
  onConnect: () => void;
  onSync: () => void;
  onDisconnect: () => void;
  onDeleteLocalData: () => void;
}) {
  const connected = status?.connection_status === "connected_read_only";
  const canDisconnect = Boolean(status?.adapter_enabled && [
    "connected_read_only",
    "disabled_connection",
    "rejected_trade_enabled",
    "disconnect_pending",
  ].includes(status.connection_status));
  return (
    <section className="sheet connection-sheet" aria-label="Wealthsimple connection">
      <div className="sheet-toolbar">
        <div><strong>WEALTHSIMPLE / SNAPTRADE</strong><span>Personal API Key · holdings access only</span></div>
        <span className={`connection-badge ${connected ? "status-good" : status?.stale ? "status-warn" : ""}`}>{connectionLabel(status)}</span>
      </div>
      <div className="connection-grid">
        <div><span>PERMISSION</span><strong>{status?.connection_permission === "read" ? "READ ONLY" : "—"}</strong></div>
        <div><span>LAST SUCCESSFUL SYNC</span><strong>{timestamp(status?.last_successful_sync_at)}</strong></div>
        <div><span>HOLDINGS AS OF</span><strong>{timestamp(status?.holdings_as_of)}</strong></div>
        <div><span>NEXT SYNC</span><strong>{status?.sync_allowed ? "AVAILABLE" : timestamp(status?.next_sync_allowed_at)}</strong></div>
        <div><span>PRICE PROVIDER</span><strong>{priceCapabilities?.provider ?? "CHECKING"}</strong></div>
        <div><span>PRICE AUTO-REFRESH</span><strong>{priceCapabilities?.automatic_refresh_supported ? `${priceCapabilities.automatic_refresh_seconds}s` : "OFF"}</strong></div>
      </div>
      {status?.warnings.map((warning) => <div className="connection-warning" key={warning}>{warning}</div>)}
      {!status?.adapter_enabled && (
        <div className="connection-note">Disabled by default. No credentials can be entered in this application. After the security audit, keys must be added manually to macOS Keychain outside Codex.</div>
      )}
      <div className="connection-actions">
        <span>Wealthsimple credentials and MFA are entered only in SnapTrade's portal.</span>
        {!connected && <button className="button primary" disabled={!status?.adapter_enabled || busy} onClick={onConnect}>CONNECT</button>}
        <button className="button" disabled={!status?.adapter_enabled || !status.sync_allowed || busy || previewOpen} onClick={onSync}>{busy ? "WORKING…" : "SYNC"}</button>
        <button className="button danger" disabled={!canDisconnect || busy} onClick={onDisconnect}>DISCONNECT</button>
        <button className="button danger quiet" disabled={busy} onClick={onDeleteLocalData}>DELETE LOCAL BROKERAGE DATA</button>
      </div>
    </section>
  );
}

function SnapTradePreviewPanel({ preview, busy, confirmed, setConfirmed, onApply, onCancel }: {
  preview: SnapTradeSyncPreview;
  busy: boolean;
  confirmed: boolean;
  setConfirmed: (value: boolean) => void;
  onApply: () => void;
  onCancel: () => void;
}) {
  const groups: { key: keyof SnapTradeSyncPreview["changes"]; label: string }[] = [
    { key: "additions", label: "ADDITIONS" },
    { key: "removals", label: "REMOVALS" },
    { key: "quantity_changes", label: "QUANTITY CHANGES" },
    { key: "cost_basis_changes", label: "COST-BASIS CHANGES" },
    { key: "cash_changes", label: "CASH CHANGES" },
  ];
  return (
    <section className="sheet sync-preview-sheet">
      <div className="sheet-toolbar">
          <div><strong>SYNC PREVIEW — ACTION REQUIRED</strong><span>Holdings as of {timestamp(preview.holdings_as_of)} · your dashboard has not been updated</span></div>
        <button className="button" disabled={busy} onClick={onCancel}>CANCEL</button>
      </div>
      <div className="change-grid">
        {groups.map((group) => (
          <div key={group.key}>
            <span>{group.label}</span>
            <strong>{preview.changes[group.key].length}</strong>
          </div>
        ))}
        <div><span>UNRESOLVED</span><strong className={preview.error_count ? "negative" : ""}>{preview.error_count}</strong></div>
      </div>
      {preview.issues.length > 0 && (
        <div className="sync-issues">
          {preview.issues.map((issue, index) => (
            <div className={issue.severity} key={`${issue.code}-${issue.symbol}-${index}`}>
              <strong>{issue.severity.toUpperCase()}</strong>
              <span>{issue.symbol ? `${issue.symbol}: ` : ""}{issue.message}</span>
            </div>
          ))}
        </div>
      )}
      <div className="change-tables">
        {groups.map((group) => preview.changes[group.key].length > 0 && (
          <table className="grid-table change-table" key={group.key}>
            <thead><tr><th>{group.label}</th><th>Before</th><th>After</th></tr></thead>
            <tbody>{preview.changes[group.key].map((change) => (
              <tr key={`${change.account_type}-${change.symbol}`}><td className="symbol-cell">{change.symbol}</td><td className="num">{change.before ?? "—"}</td><td className="num">{change.after ?? "—"}</td></tr>
            ))}</tbody>
          </table>
        ))}
      </div>
      <div className="table-scroll">
        <table className="grid-table sync-position-table">
          <thead><tr><th>#</th><th>Symbol</th><th>Name</th><th>Type</th><th>Currency</th><th>Quantity</th><th>Average cost</th><th>Account type</th></tr></thead>
          <tbody>{preview.positions.map((row) => (
            <tr key={`${row.account_alias}-${row.canonical_symbol}`}><th className="row-number">{row.row_number}</th><td className="symbol-cell">{row.canonical_symbol}</td><td>{row.security_name}</td><td>{row.asset_type}</td><td>{row.trading_currency}</td><td className="num">{number(row.quantity)}</td><td className="num">{number(row.average_cost)}</td><td>{row.account_type}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="sync-apply-bar">
        <label className="check"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed every addition, removal and changed value</label>
        <span>Applying creates a new immutable local snapshot. It cannot place an order.</span>
        <button className="button primary" disabled={busy || !confirmed || !preview.can_apply} onClick={onApply}>APPLY SNAPSHOT</button>
      </div>
    </section>
  );
}

function ColumnChooser({ visibleColumns, onToggle, onReset }: {
  visibleColumns: ColumnKey[];
  onToggle: (key: ColumnKey) => void;
  onReset: () => void;
}) {
  return (
    <details className="column-chooser">
      <summary>COLUMNS {visibleColumns.length}/{COLUMN_OPTIONS.length}</summary>
      <div className="column-menu">
        <div className="column-menu-header"><strong>VISIBLE COLUMNS</strong><button type="button" onClick={onReset}>DEFAULT</button></div>
        {COLUMN_OPTIONS.map((column) => (
          <label key={column.key}>
            <input
              type="checkbox"
              checked={visibleColumns.includes(column.key)}
              disabled={column.key === "symbol"}
              onChange={() => onToggle(column.key)}
            />
            {column.label}
          </label>
        ))}
      </div>
    </details>
  );
}

function HoldingRow({ row, index, sectorOptions, visibleColumns, selected, sectorBusy, onSelect, onSector }: {
  row: Holding;
  index: number;
  sectorOptions: SectorName[];
  visibleColumns: ColumnKey[];
  selected: boolean;
  sectorBusy: boolean;
  onSelect: () => void;
  onSector: (value: string) => void;
}) {
  const status = evidenceStatus(row);
  const gain = Number(row.unrealized_gain_loss_cad ?? 0);
  return (
    <tr className={selected ? "selected-row" : undefined} aria-selected={selected}>
      <th className="row-number" scope="row">
        <button
          type="button"
          className="row-selector"
          aria-label={`Select row ${index}: ${row.canonical_symbol}`}
          aria-pressed={selected}
          title="Select this row"
          onClick={onSelect}
        >
          {index}
        </button>
      </th>
      {visibleColumns.map((column) => {
        const classNames = [`column-${column}`];
        if (["quantity", "averageCost", "lastPrice", "marketValue", "gainLoss", "weight"].includes(column)) classNames.push("num");
        if (column === "symbol") classNames.push("symbol-cell");
        if (column === "marketValue") classNames.push("strong-cell");
        if (column === "gainLoss") classNames.push(gain >= 0 ? "positive" : "negative");
        if (column === "priceStatus") classNames.push(status.className);
        if (column === "sector") classNames.push("sector-cell");
        return (
          <td className={classNames.join(" ")} key={column}>
            <HoldingCell
              column={column}
              row={row}
              sectorOptions={sectorOptions}
              sectorBusy={sectorBusy}
              statusLabel={status.label}
              onSector={onSector}
            />
          </td>
        );
      })}
    </tr>
  );
}

function HoldingCell({ column, row, sectorOptions, sectorBusy, statusLabel, onSector }: {
  column: ColumnKey;
  row: Holding;
  sectorOptions: SectorName[];
  sectorBusy: boolean;
  statusLabel: string;
  onSector: (value: string) => void;
}) {
  switch (column) {
    case "symbol": return row.canonical_symbol;
    case "name": return row.security_name;
    case "account": return <>{row.account_alias}<small>{row.account_type}</small></>;
    case "type": return row.asset_type;
    case "exchange": return row.exchange;
    case "currency": return row.trading_currency;
    case "sector":
      if (row.asset_type === "ETF") return "Sectors from ETF holdings";
      if (row.asset_type === "CASH") return "Cash";
      return (
        <select aria-label={`Sector for ${row.canonical_symbol}`} className="cell-select" value={row.manual_sector ?? ""} disabled={sectorBusy} onChange={(event) => onSector(event.target.value)}>
          <option value="">Unclassified</option>
          {sectorOptions.map((sector) => <option key={sector}>{sector}</option>)}
        </select>
      );
    case "quantity": return number(row.quantity);
    case "averageCost": return valueWithCurrency(row.average_cost, row.trading_currency);
    case "lastPrice": return valueWithCurrency(row.price, row.price_currency);
    case "marketValue": return cad(row.market_value_cad);
    case "gainLoss": return cad(row.unrealized_gain_loss_cad);
    case "weight": return percent(row.portfolio_weight);
    case "priceStatus": return <span title="Stale means an older or imported price is being used because refresh did not return a newer quote.">{statusLabel}</span>;
    case "priceAsOf": return timestamp(row.price_timestamp);
    case "source":
      return row.price_source_url
        ? <a href={row.price_source_url} target="_blank" rel="noreferrer">{row.price_source ?? "Open source"}</a>
        : row.price_source ?? "—";
  }
}

function SectorView({ analysis }: { analysis: SectorAnalysis }) {
  return (
    <div className="sector-layout">
      <SectorPie categories={analysis.categories} />
      <div className="sector-legend-wrap">
        <table className="sector-legend">
          <thead><tr><th>Sector</th><th>Allocation</th><th>Value</th></tr></thead>
          <tbody>
            {analysis.categories.map((row) => (
              <tr key={row.sector}>
                <td><span className="legend-key" style={{ background: SECTOR_COLORS[row.sector] ?? SECTOR_COLORS.Other }} />{row.sector}</td>
                <td className="num">{percent(row.portfolio_weight)}</td>
                <td className="num">{cad(row.market_value_cad)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="coverage-line"><span>PORTFOLIO COVERAGE {percent(analysis.coverage_pct)}</span><span>ETF HOLDINGS COVERAGE {percent(analysis.etf_coverage_pct)}</span></div>
      </div>
    </div>
  );
}

function point(cx: number, cy: number, radius: number, angle: number) {
  const radians = ((angle - 90) * Math.PI) / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function slicePath(startAngle: number, endAngle: number): string {
  const start = point(120, 120, 92, endAngle);
  const end = point(120, 120, 92, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M 120 120 L ${start.x} ${start.y} A 92 92 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function SectorPie({ categories }: { categories: SectorCategory[] }) {
  const total = categories.reduce((sum, row) => sum + Number(row.portfolio_weight), 0);
  if (total <= 0) return <div className="pie-empty">NO VALUED DATA</div>;
  let cursor = 0;
  return (
    <svg className="sector-pie" viewBox="0 0 240 240" role="img" aria-label="Portfolio sector allocation pie chart">
      <title>Portfolio sector allocation</title>
      {categories.length === 1 ? (
        <circle cx="120" cy="120" r="92" fill={SECTOR_COLORS[categories[0].sector] ?? SECTOR_COLORS.Other} />
      ) : categories.map((row) => {
        const start = cursor;
        const end = cursor + (Number(row.portfolio_weight) / total) * 360;
        cursor = end;
        return <path key={row.sector} d={slicePath(start, end)} fill={SECTOR_COLORS[row.sector] ?? SECTOR_COLORS.Other}><title>{row.sector}: {percent(row.portfolio_weight)}</title></path>;
      })}
      <circle cx="120" cy="120" r="92" fill="none" stroke="var(--line-strong)" strokeWidth="1" />
    </svg>
  );
}

function EtfEvidence({ analysis }: { analysis: SectorAnalysis }) {
  return (
    <section className="sheet evidence-sheet">
      <SectionHeader title="ETF HOLDINGS DATA" meta="Issuer data used to split ETFs into sectors" />
      <div className="table-scroll">
        <table className="grid-table evidence-table">
          <thead><tr><th>ETF</th><th>Issuer</th><th>Data as of</th><th>Verified</th><th>Coverage</th><th>Status</th><th>Method</th><th>Source</th></tr></thead>
          <tbody>
            {analysis.evidence.map((row) => (
              <tr key={row.symbol}>
                <td className="symbol-cell">{row.symbol}</td>
                <td>{row.issuer ?? "—"}</td>
                <td>{row.as_of ?? "MISSING"}</td>
                <td>{row.verified_on ?? "—"}</td>
                <td className="num">{percent(row.coverage_pct)}</td>
                <td className={row.stale === true ? "status-warn" : row.stale === false ? "status-good" : "status-bad"}>{row.stale === true ? "STALE" : row.stale === false ? "CURRENT" : "MISSING"}</td>
                <td>{row.method}</td>
                <td>{row.source_url ? <a href={row.source_url} target="_blank" rel="noreferrer">Open issuer source</a> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DataQuality({ warnings }: { warnings: string[] }) {
  const unique = Array.from(new Set(warnings));
  if (unique.length === 0) return <div className="quality-ok">NO ACTIVE WARNINGS</div>;
  return <ol className="warning-list">{unique.map((warning) => <li key={warning}>{warning}</li>)}</ol>;
}

function HistoryChart({ points }: { points: HistoryPoint[] }) {
  if (points.length < 2) return <div className="chart-empty">A line appears after the next valuation snapshot.</div>;
  const values = points.map((point) => Number(point.total_cad));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values.map((value, index) => {
    const x = 4 + (index / (values.length - 1)) * 92;
    const y = 88 - ((value - min) / range) * 72;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <svg className="history-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Portfolio CAD value history">
      <line x1="4" x2="96" y1="88" y2="88" />
      <path d={path} />
    </svg>
  );
}
