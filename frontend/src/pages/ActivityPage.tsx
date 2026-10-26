import { useMemo, useState } from "react";
import { amount, dateOnly, timestamp } from "../lib/format";
import type { ActivityPayload } from "../types";
import { DataPanel, EmptyState, SourceTimestamp, ViewHeader } from "../components/ui";

const FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "All activity" },
  { value: "BUY", label: "Buys" },
  { value: "SELL", label: "Sells" },
  { value: "DISTRIBUTION", label: "Distributions" },
  { value: "DEPOSIT", label: "Deposits" },
  { value: "WITHDRAWAL", label: "Withdrawals" },
  { value: "FEE", label: "Fees" },
];

export function ActivityPage({ activity }: { activity: ActivityPayload | null }) {
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const rows = useMemo(() => (activity?.activities ?? []).filter((row) => {
    const day = row.trade_date?.slice(0, 10) ?? "";
    return (!kind || row.normalized_type === kind)
      && (!query || (row.symbol ?? "").toLowerCase().includes(query.toLowerCase()))
      && (!start || day >= start)
      && (!end || day <= end);
  }), [activity, kind, query, start, end]);
  return (
    <>
      <ViewHeader title="Activity" subtitle="Read-only completed transaction and cash history from the brokerage" asOf={activity?.coverage.source_as_of} />
      <DataPanel title="Completed activity" meta="NO ORDER ACTIONS AVAILABLE">
        <div className="table-toolbar activity-toolbar">
          <div>
            <select aria-label="Activity type" value={kind} onChange={(event) => setKind(event.target.value)}>{FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
            <input aria-label="Search activity symbol" placeholder="Search symbol" value={query} onChange={(event) => setQuery(event.target.value)} />
            <label>FROM <input aria-label="Activity start date" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
            <label>TO <input aria-label="Activity end date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
          </div>
          <strong>DAILY / CACHED</strong>
        </div>
        {!activity?.activities.length ? (
          <EmptyState title="NO COMPLETED ACTIVITIES STORED">A confirmed SnapTrade synchronization can add completed buys, sells, distributions, deposits, withdrawals and fees.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data-table activity-table">
              <thead><tr><th>Type</th><th>Holding</th><th>Date</th><th className="numeric">Quantity</th><th className="numeric">Price</th><th>Currency</th><th className="numeric">Fee</th><th className="numeric">Cash amount</th><th>Source / as-of status</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.id ?? `${row.trade_date}-${row.normalized_type}-${row.symbol}`}><td>{row.normalized_type}</td><td className="symbol">{row.symbol ?? "NOT APPLICABLE"}</td><td>{dateOnly(row.trade_date)}</td><td className="numeric">{amount(row.quantity)}</td><td className="numeric">{amount(row.price, row.currency)}</td><td>{row.currency ?? "MISSING"}</td><td className="numeric">{amount(row.fee, row.currency)}</td><td className={`numeric ${Number(row.cash_amount) > 0 ? "positive" : Number(row.cash_amount) < 0 ? "negative" : ""}`}>{amount(row.cash_amount, row.currency)}</td><td>SNAPTRADE DAILY<small>{timestamp(row.source_as_of)}</small></td></tr>)}</tbody>
            </table>
          </div>
        )}
        {activity?.warnings.length ? <ul className="warning-list">{activity.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
        <SourceTimestamp source={activity?.source} asOf={activity?.coverage.source_as_of} coverage={`${dateOnly(activity?.coverage.start)} — ${dateOnly(activity?.coverage.end)}`} status={activity?.coverage.complete ? "ALL RETURNED PAGES · LIFETIME COVERAGE NOT GUARANTEED" : "INCOMPLETE RETURNED-PAGE COVERAGE"} />
      </DataPanel>
    </>
  );
}
