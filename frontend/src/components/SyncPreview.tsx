import { dateOnly, timestamp } from "../lib/format";
import type { SnapTradeSyncPreview } from "../types";
import { DataPanel } from "./ui";

export function SyncPreview({
  preview,
  busy,
  confirmed,
  onConfirmed,
  onApply,
  onCancel,
}: {
  preview: SnapTradeSyncPreview;
  busy: boolean;
  confirmed: boolean;
  onConfirmed: (confirmed: boolean) => void;
  onApply: () => void;
  onCancel: () => void;
}) {
  const groups: Array<{ key: keyof SnapTradeSyncPreview["changes"]; label: string }> = [
    { key: "additions", label: "ADDITIONS" },
    { key: "removals", label: "REMOVALS" },
    { key: "quantity_changes", label: "QUANTITY CHANGES" },
    { key: "cost_basis_changes", label: "COST-BASIS CHANGES" },
    { key: "cash_changes", label: "CASH CHANGES" },
  ];
  const activity = preview.activity_summary ?? {
    additions: 0,
    changed_records: 0,
    date_range: { start: null, end: null },
    type_counts: {},
    missing_symbols: [],
    unsupported_activity_types: [],
    coverage_start: null,
    coverage_end: null,
    incomplete_initial_sync: false,
    warning: null,
    accounts: [],
  };
  const uniqueIssues = Array.from(
    new Map(preview.issues.map((issue) => [JSON.stringify(issue), issue])).entries(),
  );
  return (
    <DataPanel
      title="Synchronization preview · action required"
      className="sync-preview"
      actions={<button className="action" type="button" disabled={busy} onClick={onCancel}>CANCEL</button>}
    >
      <div className="preview-intro">
        Holdings as of {timestamp(preview.holdings_as_of)} · Nothing is applied to portfolio or activity history until you confirm.
      </div>
      <div className="preview-counts">
        {groups.map((group) => (
          <div key={group.key}>
            <span>{group.label}</span>
            <strong>{preview.changes[group.key].length}</strong>
          </div>
        ))}
        <div><span>UNRESOLVED</span><strong className={preview.error_count ? "negative" : ""}>{preview.error_count}</strong></div>
      </div>
      <div className="preview-counts activity-counts">
        <div><span>ACTIVITY ADDITIONS</span><strong>{activity.additions}</strong></div>
        <div><span>CHANGED RECORDS</span><strong>{activity.changed_records}</strong></div>
        <div><span>ACTIVITY FROM</span><strong>{dateOnly(activity.date_range.start)}</strong></div>
        <div><span>ACTIVITY TO</span><strong>{dateOnly(activity.date_range.end)}</strong></div>
        <div><span>MISSING SYMBOLS</span><strong>{activity.missing_symbols.length}</strong></div>
        <div><span>UNSUPPORTED TYPES</span><strong>{activity.unsupported_activity_types.length}</strong></div>
      </div>
      <div className="activity-types">
        <strong>COMPLETED ACTIVITY TYPES</strong>
        <span>{Object.entries(activity.type_counts).map(([type, count]) => `${type} ${count}`).join(" · ") || "NO ACTIVITY RETURNED"}</span>
        <span className={activity.incomplete_initial_sync ? "warning" : "positive"}>
          {activity.incomplete_initial_sync ? "INCOMPLETE INITIAL SYNCHRONIZATION" : "BOUNDED PAGINATION COMPLETE"}
        </span>
      </div>
      {preview.issues.length > 0 && (
        <div className="issue-list">
          {uniqueIssues.map(([issueKey, issue]) => (
            <div className={issue.severity} key={issueKey}>
              <strong>{issue.severity.toUpperCase()} · {issue.code}</strong>
              <span>{issue.symbol ? `${issue.symbol} · ` : ""}{issue.message}</span>
            </div>
          ))}
        </div>
      )}
      <div className="table-wrap">
        <table className="data-table preview-table">
          <thead><tr><th>#</th><th>Symbol</th><th>Name</th><th>Type</th><th>Currency</th><th className="numeric">Quantity</th><th className="numeric">Average cost</th><th>Account type</th></tr></thead>
          <tbody>
            {preview.positions.map((row) => (
              <tr key={`${row.account_alias}-${row.canonical_symbol}`}>
                <td>{row.row_number}</td><td className="symbol">{row.canonical_symbol}</td><td>{row.security_name}</td><td>{row.asset_type}</td><td>{row.trading_currency}</td><td className="numeric">{row.quantity}</td><td className="numeric">{row.average_cost ?? "—"}</td><td>{row.account_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="apply-bar">
        <label>
          <input type="checkbox" checked={confirmed} onChange={(event) => onConfirmed(event.target.checked)} />
          <span><strong>REQUIRED</strong> · I reviewed holdings and completed-activity changes.</span>
        </label>
        <span>Apply creates an immutable local snapshot. It cannot place or modify an order.</span>
        <button className="action primary" type="button" disabled={busy || !preview.can_apply || !confirmed} onClick={onApply}>APPLY SNAPSHOT</button>
      </div>
    </DataPanel>
  );
}
