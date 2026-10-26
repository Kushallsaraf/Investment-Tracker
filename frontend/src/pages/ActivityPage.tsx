import { type FormEvent, useMemo, useState } from "react";
import { amount, dateOnly, usd } from "../lib/format";
import type { Activity, ActivityInput, ActivityPayload, ActivityType } from "../types";
import { DataPanel, EmptyState, SourceTimestamp, ViewHeader } from "../components/ui";

const TYPE_LABELS: Record<ActivityType, string> = {
  BUY: "Buy",
  SELL: "Sell",
  DIVIDEND: "Dividend",
  DEPOSIT: "Deposit",
  WITHDRAWAL: "Withdrawal",
  FEE: "Fee",
  INTEREST: "Interest",
  WITHHOLDING_TAX: "Withholding tax",
  OTHER: "Other",
};
const TYPES = Object.keys(TYPE_LABELS) as ActivityType[];
const SECURITY_TYPES: ActivityType[] = ["BUY", "SELL", "DIVIDEND"];

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function ActivityPage({
  activity,
  busy,
  onCreate,
  onDelete,
}: {
  activity: ActivityPayload | null;
  busy: boolean;
  onCreate: (input: ActivityInput) => Promise<boolean>;
  onDelete: (activity: Activity) => void;
}) {
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const rows = useMemo(() => (activity?.activities ?? []).filter((row) => (
    (!kind || row.activity_type === kind)
      && (!query || (row.symbol ?? "").toLowerCase().includes(query.toLowerCase()))
      && (!start || row.trade_date >= start)
      && (!end || row.trade_date <= end)
  )), [activity, kind, query, start, end]);
  return (
    <>
      <ViewHeader title="Activity" subtitle="Local ledger of trades, dividends, cash movements and fees · recording an activity never places an order" asOf={activity?.coverage.end} />
      <ActivityForm busy={busy} onCreate={onCreate} />
      <DataPanel title="Activity ledger" meta="NO ORDER ACTIONS AVAILABLE">
        <div className="table-toolbar activity-toolbar">
          <div>
            <select aria-label="Activity type" value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">All activity</option>
              {TYPES.map((type) => <option key={type} value={type}>{TYPE_LABELS[type]}</option>)}
            </select>
            <input aria-label="Search activity symbol" placeholder="Search symbol" value={query} onChange={(event) => setQuery(event.target.value)} />
            <label>FROM <input aria-label="Activity start date" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
            <label>TO <input aria-label="Activity end date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
          </div>
          <strong>{activity?.coverage.count ?? 0} RECORDED</strong>
        </div>
        {!activity?.activities.length ? (
          <EmptyState title="NO ACTIVITIES RECORDED">Record buys, sells, dividends, deposits, withdrawals and fees above, or load the demo portfolio in Settings.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data-table activity-table">
              <thead><tr><th>Type</th><th>Holding</th><th>Date</th><th className="numeric">Quantity</th><th className="numeric">Price</th><th className="numeric">Fee</th><th className="numeric">Cash amount</th><th>Note / origin</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.activity_type}</td>
                  <td className="symbol">{row.symbol ?? "NOT APPLICABLE"}</td>
                  <td>{dateOnly(row.trade_date)}</td>
                  <td className="numeric">{amount(row.quantity)}</td>
                  <td className="numeric">{row.price == null ? "—" : usd(row.price)}</td>
                  <td className="numeric">{row.fee == null ? "—" : usd(row.fee)}</td>
                  <td className={`numeric ${Number(row.cash_amount) > 0 ? "positive" : Number(row.cash_amount) < 0 ? "negative" : ""}`}>{row.cash_amount == null ? "—" : usd(row.cash_amount)}</td>
                  <td>{row.note || "—"}<small>{row.data_origin === "demo" ? "SYNTHETIC DEMO" : "MANUAL"}</small></td>
                  <td><button className="action danger" type="button" aria-label={["Delete", row.activity_type, row.symbol, row.trade_date].filter(Boolean).join(" ")} disabled={busy} onClick={() => onDelete(row)}>DELETE</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {activity?.warnings.length ? <ul className="warning-list">{activity.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
        <SourceTimestamp source={activity?.source} asOf={activity?.coverage.end} coverage={activity?.coverage.count ? `${dateOnly(activity.coverage.start)} — ${dateOnly(activity.coverage.end)}` : "NO ACTIVITIES"} status="HOLDINGS ARE EDITED SEPARATELY" />
      </DataPanel>
    </>
  );
}

function ActivityForm({ busy, onCreate }: { busy: boolean; onCreate: (input: ActivityInput) => Promise<boolean> }) {
  const [type, setType] = useState<ActivityType>("DIVIDEND");
  const [date, setDate] = useState(today);
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [cashAmount, setCashAmount] = useState("");
  const [note, setNote] = useState("");
  const needsSymbol = SECURITY_TYPES.includes(type);
  const isTrade = type === "BUY" || type === "SELL";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const saved = await onCreate({
      activity_type: type,
      trade_date: date,
      symbol: needsSymbol || symbol.trim() ? symbol.trim() || null : null,
      quantity: isTrade ? quantity.trim() || null : null,
      price: isTrade ? price.trim() || null : null,
      cash_amount: cashAmount.trim() || null,
      note: note.trim(),
    });
    if (saved) {
      setQuantity("");
      setPrice("");
      setCashAmount("");
      setNote("");
    }
  }

  return (
    <DataPanel title="Record an activity" meta="USD · LOCAL LEDGER ONLY">
      <form className="editor-form" onSubmit={(event) => void submit(event)}>
        <div className="form-grid four">
          <label>TYPE<select aria-label="New activity type" value={type} onChange={(event) => setType(event.target.value as ActivityType)}>{TYPES.map((option) => <option key={option} value={option}>{TYPE_LABELS[option]}</option>)}</select></label>
          <label>DATE<input aria-label="New activity date" type="date" value={date} onChange={(event) => setDate(event.target.value)} required /></label>
          <label>SYMBOL<input aria-label="New activity symbol" placeholder={needsSymbol ? "Required" : "Optional"} value={symbol} onChange={(event) => setSymbol(event.target.value)} required={needsSymbol} maxLength={12} /></label>
          <label>CASH AMOUNT (USD)<input aria-label="New activity cash amount" inputMode="decimal" placeholder={isTrade ? "Optional · negative for buys" : "Required · negative for outflows"} value={cashAmount} onChange={(event) => setCashAmount(event.target.value)} required={!isTrade} /></label>
          {isTrade && <label>QUANTITY<input aria-label="New activity quantity" inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>}
          {isTrade && <label>PRICE (USD)<input aria-label="New activity price" inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} /></label>}
          <label>NOTE<input aria-label="New activity note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} /></label>
        </div>
        <div className="form-actions">
          <span className="panel-note">Recording a buy or sell does not change holdings. Update the position on the Holdings tab.</span>
          <button className="action primary" type="submit" disabled={busy}>RECORD ACTIVITY</button>
        </div>
      </form>
    </DataPanel>
  );
}
