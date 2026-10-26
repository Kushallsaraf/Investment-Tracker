import { useEffect, useMemo, useState } from "react";
import { amount, cad, decisionLabel, percent, signedCad, statusLabel, statusTone, timestamp } from "../lib/format";
import type { DecisionName, Holding, JournalPayload, Portfolio, SectorAnalysis, SectorName } from "../types";
import { DataPanel, EmptyState, SourceTimestamp, ViewHeader } from "../components/ui";

export type ColumnKey =
  | "symbol" | "name" | "account" | "type" | "exchange" | "currency" | "sector"
  | "quantity" | "averageCost" | "lastPrice" | "marketValue" | "gainLoss" | "weight"
  | "decision" | "priceStatus" | "priceAsOf" | "source";

const COLUMNS: Array<{ key: ColumnKey; label: string }> = [
  { key: "symbol", label: "Symbol" }, { key: "name", label: "Name" },
  { key: "account", label: "Account" }, { key: "type", label: "Type" },
  { key: "exchange", label: "Exchange" }, { key: "currency", label: "Currency" },
  { key: "sector", label: "Sector" }, { key: "quantity", label: "Quantity" },
  { key: "averageCost", label: "Average cost" }, { key: "lastPrice", label: "Last price" },
  { key: "marketValue", label: "Market value" }, { key: "gainLoss", label: "Gain/loss" },
  { key: "weight", label: "Weight" }, { key: "decision", label: "My decision" },
  { key: "priceStatus", label: "Price status" }, { key: "priceAsOf", label: "Price timestamp" },
  { key: "source", label: "Price source" },
];

const DEFAULT_COLUMNS: ColumnKey[] = [
  "symbol", "name", "type", "sector", "quantity", "averageCost", "lastPrice",
  "marketValue", "gainLoss", "weight", "decision", "priceStatus",
];
const COLUMN_STORAGE_KEY = "portfolio-manager.visible-columns.v1";

function loadColumns(): ColumnKey[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem(COLUMN_STORAGE_KEY) ?? "null");
    if (Array.isArray(saved)) {
      const allowed = new Set(COLUMNS.map((column) => column.key));
      const selected = saved.filter((key): key is ColumnKey => allowed.has(key));
      if (!selected.includes("symbol")) selected.unshift("symbol");
      return COLUMNS.map((column) => column.key).filter((key) => selected.includes(key));
    }
  } catch {
    // Invalid local display preferences are safely replaced with approved defaults.
  }
  return DEFAULT_COLUMNS;
}

const DECISIONS: DecisionName[] = ["WATCH", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "EXIT_CANDIDATE"];

export function HoldingsPage({
  portfolio,
  sectors,
  journal,
  busy,
  onRefresh,
  onDelete,
  onSector,
  onDecision,
}: {
  portfolio: Portfolio | null;
  sectors: SectorAnalysis | null;
  journal: JournalPayload | null;
  busy: boolean;
  onRefresh: () => void;
  onDelete: (holding: Holding) => void;
  onSector: (instrumentId: string, sector: SectorName | null) => void;
  onDecision: (instrumentId: string, decision: DecisionName) => void;
}) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(loadColumns);
  useEffect(() => {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibleColumns));
  }, [visibleColumns]);
  const holdings = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (portfolio?.holdings ?? []).filter((row) => (
      !needle || `${row.canonical_symbol} ${row.security_name}`.toLowerCase().includes(needle)
    ));
  }, [portfolio, query]);
  const selected = holdings.find((row) => row.position_id === selectedId) ?? null;
  const decisions = new Map(
    (journal?.entries ?? []).map((entry) => [entry.holding.instrument_id, entry.decision?.decision ?? "WATCH"]),
  );
  const etfEvidence = new Map((sectors?.evidence ?? []).map((row) => [row.symbol, row]));

  useEffect(() => {
    function deleteKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing = target?.isContentEditable
        || ["INPUT", "SELECT", "TEXTAREA"].includes(target?.tagName ?? "")
        || (target?.tagName === "BUTTON" && !target.closest(".row-number"));
      if (!editing && !event.repeat && selected && (event.key === "Delete" || event.key === "Backspace")) {
        event.preventDefault();
        onDelete(selected);
      }
    }
    window.addEventListener("keydown", deleteKey);
    return () => window.removeEventListener("keydown", deleteKey);
  }, [onDelete, selected]);

  function toggleColumn(key: ColumnKey) {
    if (key === "symbol") return;
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return COLUMNS.map((column) => column.key).filter((column) => next.has(column));
    });
  }

  return (
    <>
      <ViewHeader
        title="Holdings"
        subtitle="Spreadsheet view · click a row, then use Delete to remove it from the local snapshot"
        asOf={portfolio?.source_as_of ?? portfolio?.created_at}
      />
      <DataPanel title="Holdings worksheet" meta={portfolio ? `${portfolio.total_positions} rows` : "NO SNAPSHOT"}>
        <div className="table-toolbar">
          <div>
            <input
              aria-label="Search holdings"
              placeholder="Search symbol or security name"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <ColumnChooser visible={visibleColumns} onToggle={toggleColumn} onReset={() => setVisibleColumns(DEFAULT_COLUMNS)} />
          </div>
          <div>
            <button className="action danger" type="button" disabled={!selected || busy} onClick={() => selected && onDelete(selected)}>DELETE ROW</button>
            <button className="action primary roster" type="button" disabled={!portfolio || busy} onClick={onRefresh}>{busy ? "REFRESHING…" : "REFRESH PRICES"}</button>
          </div>
        </div>
        {!portfolio ? (
          <EmptyState title="NO HOLDINGS SNAPSHOT">Synchronize and approve holdings in Settings.</EmptyState>
        ) : (
          <div className="table-wrap holdings-table-wrap">
            <table className="data-table holdings-table" style={{ minWidth: Math.max(900, visibleColumns.length * 112 + 42) }}>
              <thead><tr><th className="row-number">#</th>{visibleColumns.map((column) => <th key={column} className={numericColumn(column) ? "numeric" : undefined}>{COLUMNS.find((candidate) => candidate.key === column)?.label}</th>)}</tr></thead>
              <tbody>
                {holdings.map((row, index) => (
                  <tr key={row.position_id} className={row.position_id === selectedId ? "selected-row" : undefined} aria-selected={row.position_id === selectedId}>
                    <th className="row-number" scope="row">
                      <button type="button" aria-label={`Select row ${index + 1}: ${row.canonical_symbol}`} aria-pressed={row.position_id === selectedId} onClick={() => setSelectedId((current) => current === row.position_id ? null : row.position_id)}>{index + 1}</button>
                    </th>
                    {visibleColumns.map((column) => (
                      <td key={column} className={`${numericColumn(column) ? "numeric " : ""}${column === "symbol" ? "symbol " : ""}${column === "priceStatus" ? statusTone(row) : ""}`.trim()}>
                        <HoldingCell
                          column={column}
                          row={row}
                          decision={(decisions.get(row.instrument_id) ?? "WATCH") as DecisionName}
                          sectorOptions={sectors?.sector_options ?? []}
                          etfEvidence={etfEvidence.get(row.canonical_symbol)}
                          onSector={onSector}
                          onDecision={onDecision}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="worksheet-guide">
          <strong>PRICE STATUS</strong>
          <span>END OF DAY = latest market close.</span>
          <span>STALE = the quote is old; check its exact timestamp and source.</span>
          <span>MISSING = no usable independent quote.</span>
        </div>
        <div className="worksheet-status">
          {selected ? `1 row selected · ${selected.canonical_symbol} · Press Delete/Backspace or choose Delete Row.` : "Click a row number to select a holding."}
          <span>Deleting changes only the local snapshot. It is not a Wealthsimple sale.</span>
        </div>
        <SourceTimestamp source="Independent market prices and immutable local snapshot" asOf={portfolio?.created_at} coverage={percent(portfolio?.position_coverage_pct)} status="NO BROKERAGE ACTIONS" />
      </DataPanel>
    </>
  );
}

function numericColumn(column: ColumnKey): boolean {
  return ["quantity", "averageCost", "lastPrice", "marketValue", "gainLoss", "weight"].includes(column);
}

function ColumnChooser({
  visible,
  onToggle,
  onReset,
}: {
  visible: ColumnKey[];
  onToggle: (key: ColumnKey) => void;
  onReset: () => void;
}) {
  return (
    <details className="column-chooser">
      <summary>COLUMNS {visible.length}/{COLUMNS.length}</summary>
      <div className="column-menu">
        <div><strong>VISIBLE COLUMNS</strong><button type="button" onClick={onReset}>DEFAULT</button></div>
        {COLUMNS.map((column) => (
          <label key={column.key}>
            <input type="checkbox" checked={visible.includes(column.key)} disabled={column.key === "symbol"} onChange={() => onToggle(column.key)} />
            <span>{column.label}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

function HoldingCell({
  column,
  row,
  decision,
  sectorOptions,
  etfEvidence,
  onSector,
  onDecision,
}: {
  column: ColumnKey;
  row: Holding;
  decision: DecisionName;
  sectorOptions: SectorName[];
  etfEvidence?: { coverage_pct: string; as_of: string | null; stale: boolean | null };
  onSector: (instrumentId: string, sector: SectorName | null) => void;
  onDecision: (instrumentId: string, decision: DecisionName) => void;
}) {
  switch (column) {
    case "symbol": return row.canonical_symbol;
    case "name": return row.security_name;
    case "account": return <>{row.account_alias}<small>{row.account_type}</small></>;
    case "type": return row.asset_type;
    case "exchange": return row.exchange;
    case "currency": return row.trading_currency;
    case "sector":
      if (row.asset_type === "ETF") {
        return <span title={etfEvidence ? `Issuer evidence as of ${etfEvidence.as_of}; ${percent(etfEvidence.coverage_pct)} covered` : "No supported issuer holdings profile"}>LOOK-THROUGH · {etfEvidence ? percent(etfEvidence.coverage_pct) : "UNKNOWN"}</span>;
      }
      if (row.asset_type === "CASH") return "Cash";
      return (
        <select aria-label={`Sector for ${row.canonical_symbol}`} className="cell-select" value={row.manual_sector ?? ""} onChange={(event) => onSector(row.instrument_id, (event.target.value || null) as SectorName | null)}>
          <option value="">Unknown</option>
          {sectorOptions.map((sector) => <option key={sector}>{sector}</option>)}
        </select>
      );
    case "quantity": return amount(row.quantity);
    case "averageCost": return amount(row.average_cost, row.trading_currency);
    case "lastPrice": return amount(row.price, row.price_currency);
    case "marketValue": return cad(row.market_value_cad);
    case "gainLoss": return <span className={Number(row.unrealized_gain_loss_cad) >= 0 ? "positive" : "negative"}>{signedCad(row.unrealized_gain_loss_cad)}</span>;
    case "weight": return percent(row.portfolio_weight);
    case "decision":
      if (row.asset_type === "CASH") return "—";
      return (
        <select aria-label={`My decision for ${row.canonical_symbol}`} className="cell-select" value={decision} onChange={(event) => onDecision(row.instrument_id, event.target.value as DecisionName)}>
          {DECISIONS.map((option) => <option key={option} value={option}>{decisionLabel(option)}</option>)}
        </select>
      );
    case "priceStatus": return <span title={`Observed ${timestamp(row.price_timestamp)} · fetched ${timestamp(row.price_fetched_at)} · ${row.price_source ?? "missing source"}`}>{statusLabel(row)}</span>;
    case "priceAsOf": return timestamp(row.price_timestamp);
    case "source": return row.price_source_url ? <a href={row.price_source_url} target="_blank" rel="noreferrer">{row.price_source ?? "Open source"}</a> : row.price_source ?? "MISSING";
  }
}
