import { type FormEvent, useEffect, useState } from "react";
import { resetPeers, savePeers } from "../api";
import { DataPanel } from "../components/ui";
import { dateOnly, multiple, price, signedPercent, timestamp, usdCompact } from "../lib/format";
import type { DatedMetric, Fundamentals, InsiderActivity, PeerComparison, PeerRow, ValuationBand } from "../types";

export type Loadable<T> = { symbol: string; data: T | null; error: string | null };

/** Load per-ticker data once at page level so summary cards and drawers share one request. */
export function useSymbolData<T>(symbol: string, load: (symbol: string) => Promise<T>): [Loadable<T> | null, (data: T) => void] {
  const [state, setState] = useState<Loadable<T> | null>(null);
  useEffect(() => {
    let cancelled = false;
    setState(null);
    load(symbol)
      .then((data) => { if (!cancelled) setState({ symbol, data, error: null }); })
      .catch((cause) => { if (!cancelled) setState({ symbol, data: null, error: cause instanceof Error ? cause.message : "Unavailable" }); });
    return () => { cancelled = true; };
  }, [symbol, load]);
  return [state, (data: T) => setState({ symbol, data, error: null })];
}

function tone(value: number | null | undefined): string {
  if (value == null) return "";
  return value >= 0 ? "positive" : "negative";
}

function PanelState({ state, label }: { state: Loadable<unknown> | null; label: string }) {
  if (!state) return <p className="panel-note">Loading {label} from SEC EDGAR…</p>;
  if (state.error) {
    return (
      <div className="panel-state" role="status">
        <strong>NOT AVAILABLE</strong>
        <span>{state.error}</span>
      </div>
    );
  }
  return null;
}

function NotApplicable({ reason }: { reason: string }) {
  return <div className="panel-state"><strong>NOT APPLICABLE</strong><span>{reason}</span></div>;
}

function MetricRow({ label, metric, format, signed = false }: { label: string; metric: DatedMetric; format: (value: number) => string; signed?: boolean }) {
  return (
    <div className="metric-row" title={metric.as_of ? `As of ${metric.as_of}` : metric.note ?? undefined}>
      <span>{label}</span>
      {metric.value == null
        ? <strong className="unavailable" title={metric.note ?? undefined}>N/A</strong>
        : <strong className={signed ? tone(metric.value) : ""}>{format(metric.value)}</strong>}
    </div>
  );
}

const ratioPercent = (value: number) => signedPercent(value, 1).replace("+", "");
const growthPercent = (value: number) => signedPercent(value, 1);

function BandRow({ band }: { band: ValuationBand }) {
  if (band.status !== "available" || band.min == null || band.max == null || band.current == null) {
    return (
      <div className="band-row">
        <span>{band.metric}</span>
        <small>{band.current == null ? "N/A" : multiple(band.current)} · {band.note ?? "History unavailable"}</small>
      </div>
    );
  }
  const span = band.max - band.min || 1;
  const position = Math.min(1, Math.max(0, (band.current - band.min) / span));
  const median = Math.min(1, Math.max(0, ((band.median ?? band.min) - band.min) / span));
  const percentile = Math.round((band.percentile ?? 0) * 100);
  return (
    <div className="band-row">
      <span>{band.metric} <b>{multiple(band.current)}</b></span>
      <div className="band-track" role="img" aria-label={`${band.metric} ${multiple(band.current)}, ${percentile}th percentile of ${band.observations} quarters`}>
        <i className="band-median" style={{ left: `${median * 100}%` }} />
        <i className="band-current" style={{ left: `${position * 100}%` }} />
      </div>
      <small>{multiple(band.min)} – {multiple(band.max)} · median {multiple(band.median)} · {percentile}th percentile · {band.observations} quarters</small>
    </div>
  );
}

export function FundamentalsPanel({ state }: { state: Loadable<Fundamentals> | null }) {
  const data = state?.data;
  const meta = data?.applicable ? `TTM · ${dateOnly(data.period.ttm_end)}` : "SEC EDGAR";
  return (
    <DataPanel title="Fundamentals" meta={meta}>
      <PanelState state={state} label="fundamentals" />
      {data && !data.applicable && <NotApplicable reason={data.reason} />}
      {data?.applicable && (
        <>
          <div className="metric-list dense">
            <MetricRow label="Market cap" metric={data.valuation.market_cap} format={usdCompact} />
            <MetricRow label="P/E (TTM)" metric={data.valuation.pe_ttm} format={multiple} />
            <MetricRow label="P/S (TTM)" metric={data.valuation.ps_ttm} format={multiple} />
            <MetricRow label="EV / EBITDA" metric={data.valuation.ev_ebitda} format={multiple} />
            <MetricRow label="FCF yield" metric={data.valuation.fcf_yield} format={ratioPercent} />
            <MetricRow label="Revenue growth (TTM)" metric={data.growth.revenue_ttm_yoy} format={growthPercent} signed />
            <MetricRow label="Revenue growth (quarter)" metric={data.growth.revenue_quarter_yoy} format={growthPercent} signed />
            <MetricRow label="Gross margin" metric={data.profitability.gross_margin} format={ratioPercent} />
            <MetricRow label="Operating margin" metric={data.profitability.operating_margin} format={ratioPercent} />
            <MetricRow label="Net cash" metric={data.balance_sheet.net_cash} format={usdCompact} signed />
          </div>
          <div className="band-list">
            <span className="compact-label">Valuation vs own 5-year history</span>
            <BandRow band={data.valuation_history.pe} />
            <BandRow band={data.valuation_history.ps} />
          </div>
          {data.notes.length > 0 && <ul className="warning-list">{data.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
          {data.stale && <div className="panel-warning">SEC data could not be refreshed; showing the last saved copy.</div>}
          <div className="source-line">
            <span>SEC EDGAR 10-K/10-Q · {data.sic_description ?? "Industry not reported"}</span>
            {data.latest_filing && <a href={data.latest_filing.url} target="_blank" rel="noreferrer">LATEST {data.latest_filing.form} · FILED {dateOnly(data.latest_filing.filed)}</a>}
            <span>FETCHED · {timestamp(data.fetched_at)}</span>
          </div>
        </>
      )}
    </DataPanel>
  );
}

export function InsiderPanel({ state }: { state: Loadable<InsiderActivity> | null }) {
  const data = state?.data;
  return (
    <DataPanel title="Insider activity" meta={data?.applicable ? `FORM 4 · SINCE ${dateOnly(data.since).toUpperCase()}` : "SEC FORM 4"}>
      <PanelState state={state} label="insider filings" />
      {data && !data.applicable && <NotApplicable reason={data.reason} />}
      {data?.applicable && (
        <>
          <div className="metric-list dense">
            <div className="metric-row"><span>Open-market buys</span><strong className={data.summary.purchase_value ? "positive" : ""}>{usdCompact(data.summary.purchase_value)} · {data.summary.buyers} buyer{data.summary.buyers === 1 ? "" : "s"}</strong></div>
            <div className="metric-row"><span>Open-market sales</span><strong className={data.summary.sale_value ? "negative" : ""}>{usdCompact(data.summary.sale_value)} · {data.summary.sellers} seller{data.summary.sellers === 1 ? "" : "s"}</strong></div>
            <div className="metric-row"><span>Of sales, pre-planned (10b5-1)</span><strong>{usdCompact(data.summary.planned_sale_value)}</strong></div>
            <div className="metric-row"><span>Net open-market</span><strong className={tone(data.summary.net_value)}>{usdCompact(data.summary.net_value)}</strong></div>
          </div>
          {data.transactions.length === 0 ? (
            <p className="panel-note">No Form 4 transactions were filed in the last {data.days} days.</p>
          ) : (
            <ul className="insider-list">
              {data.transactions.slice(0, 6).map((row) => (
                <li key={`${row.url}-${row.date}-${row.code}-${row.shares}`}>
                  <span className="insider-date">{row.date ? dateOnly(row.date) : "—"}</span>
                  <span className="insider-who"><a href={row.url} target="_blank" rel="noreferrer">{row.owner}</a><small>{row.role}</small></span>
                  <span className={`insider-what ${row.code === "P" ? "positive" : row.code === "S" ? "negative" : ""}`}>{row.description}{row.planned_10b5_1 ? " · 10b5-1" : ""}<small>{row.value == null ? `${row.shares ?? "—"} shares` : `${usdCompact(row.value)} @ ${price(row.price)}`}</small></span>
                </li>
              ))}
            </ul>
          )}
          {data.warnings.map((warning) => <div className="panel-warning" key={warning}>{warning}</div>)}
          <div className="source-line"><span>{data.filings} FORM 4 FILINGS</span><span>LATEST · {dateOnly(data.latest_filing)}</span><span>Grants, exercises and tax withholding excluded from totals</span></div>
        </>
      )}
    </DataPanel>
  );
}

export function PeersPanel({
  symbol,
  state,
  setData,
  onOpenSymbol,
}: {
  symbol: string;
  state: Loadable<PeerComparison> | null;
  setData: (data: PeerComparison) => void;
  onOpenSymbol: (symbol: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const data = state?.data;

  useEffect(() => {
    setEditing(false);
    setSaveError(null);
  }, [symbol]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setData(await savePeers(symbol, draft.split(/[\s,]+/).filter(Boolean)));
      setEditing(false);
      setSaveError(null);
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "Peers could not be saved");
    }
  }

  async function reset() {
    try {
      setData(await resetPeers(symbol));
      setEditing(false);
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "Peers could not be reset");
    }
  }

  const meta = data?.applicable ? (data.list_source === "USER" ? "YOUR LIST" : `SIC ${data.sic ?? "—"}`) : "PEERS";
  return (
    <DataPanel
      title="Peers"
      meta={meta}
      actions={data?.applicable ? (
        <span className="panel-actions">
          <span>{meta}</span>
          <button className="action" type="button" onClick={() => { setDraft(data.peers.join(", ")); setEditing((open) => !open); }}>{editing ? "Cancel" : "Edit peers"}</button>
        </span>
      ) : undefined}
    >
      <PanelState state={state} label="peers" />
      {data && !data.applicable && <NotApplicable reason={data.reason} />}
      {data?.applicable && (
        <>
          {editing && (
            <form className="peer-editor" onSubmit={(event) => void submit(event)}>
              <input aria-label="Peer tickers" placeholder="TSM, UMC, INTC" value={draft} onChange={(event) => setDraft(event.target.value.toUpperCase())} />
              <button className="action primary" type="submit">Save</button>
              <button className="action" type="button" onClick={() => void reset()}>Reset to industry</button>
            </form>
          )}
          {saveError && <div className="panel-warning" role="alert">{saveError}</div>}
          <div className="table-wrap">
            <table className="data-table peers-table">
              <thead><tr><th>Symbol</th><th className="numeric">Mkt cap</th><th className="numeric">P/E</th><th className="numeric">P/S</th><th className="numeric">EV/EBITDA</th><th className="numeric">Rev growth</th><th className="numeric">Op margin</th><th className="numeric">3M</th></tr></thead>
              <tbody>{data.rows.map((row) => <PeerTableRow key={row.symbol} row={row} current={row.symbol === data.symbol} onOpen={onOpenSymbol} />)}</tbody>
            </table>
          </div>
          {data.rows.length === 1 && <p className="panel-note">No peers yet. Choose Edit peers to add tickers.</p>}
          <div className="source-line"><span>{data.list_source === "USER" ? "Peers chosen by you" : `Seeded from SEC industry code ${data.sic ?? ""}${data.sic_description ? ` · ${data.sic_description}` : ""} · larger companies first`}</span><span>TTM figures from each company's latest filings</span></div>
        </>
      )}
    </DataPanel>
  );
}

function PeerTableRow({ row, current, onOpen }: { row: PeerRow; current: boolean; onOpen: (symbol: string) => void }) {
  const cell = (value: string) => <td className="numeric">{value}</td>;
  return (
    <tr className={current ? "selected-row" : undefined}>
      <td className="symbol">
        {current ? row.symbol : <button type="button" className="link-button" onClick={() => onOpen(row.symbol)}>{row.symbol}</button>}
        <small>{row.name ?? ""}</small>
      </td>
      {row.available ? (
        <>
          {cell(usdCompact(row.market_cap))}
          {cell(multiple(row.pe_ttm))}
          {cell(multiple(row.ps_ttm))}
          {cell(multiple(row.ev_ebitda))}
          <td className={`numeric ${tone(row.revenue_growth)}`}>{signedPercent(row.revenue_growth, 1)}</td>
          {cell(row.operating_margin == null ? "—" : ratioPercent(row.operating_margin))}
        </>
      ) : (
        <td colSpan={6} className="unavailable-cell">{row.reason ?? "Not available"}</td>
      )}
      <td className={`numeric ${tone(row.return_3m)}`}>{signedPercent(row.return_3m, 1)}</td>
    </tr>
  );
}
