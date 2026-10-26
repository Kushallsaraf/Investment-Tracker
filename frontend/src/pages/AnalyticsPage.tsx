import { useState } from "react";
import { percent } from "../lib/format";
import type { Analytics, SectorAnalysis } from "../types";
import { DataPanel, Meter, MissingDataWarning, SourceTimestamp, ViewHeader } from "../components/ui";

const SUBTABS = ["Diversification", "Performance", "Risk", "ETF look-through"] as const;
type AnalyticsTab = (typeof SUBTABS)[number];

export function AnalyticsPage({
  analytics,
  sectors,
}: {
  analytics: Analytics | null;
  sectors: SectorAnalysis | null;
}) {
  const [tab, setTab] = useState<AnalyticsTab>("Diversification");
  return (
    <>
      <ViewHeader title="Analytics" subtitle="Transparent measurements with data coverage, sources and as-of dates" asOf={analytics?.generated_at} />
      <div className="sub-navigation" role="tablist" aria-label="Analytics views">
        {SUBTABS.map((name) => <button type="button" key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name}</button>)}
      </div>
      {!analytics ? <MissingDataWarning reason="Analytics have not loaded." /> : (
        <>
          {tab === "Diversification" && <Diversification analytics={analytics} sectors={sectors} />}
          {tab === "Performance" && <Performance analytics={analytics} />}
          {tab === "Risk" && <Risk analytics={analytics} />}
          {tab === "ETF look-through" && <EtfLookthrough analytics={analytics} />}
        </>
      )}
    </>
  );
}

function Diversification({ analytics, sectors }: { analytics: Analytics; sectors: SectorAnalysis | null }) {
  const concentration = analytics.concentration;
  return (
    <div className="analytics-grid">
      <DataPanel title="Sector allocation" meta={`${percent(sectors?.coverage_pct)} KNOWN`}>
        <div className="panel-body">
          {(sectors?.categories ?? []).length ? sectors?.categories.map((row) => (
            <Meter key={row.sector} label={row.sector} value={Number(row.portfolio_weight)} />
          )) : <MissingDataWarning reason="No valued sector allocation is available. Stocks remain Unknown until classified; unsupported ETFs remain Unknown." />}
        </div>
        <SourceTimestamp source="User classifications and explicitly supported issuer profiles" asOf={sectors?.calculated_at} coverage={percent(sectors?.coverage_pct)} />
      </DataPanel>
      <DataPanel title="Concentration" meta={concentration.status.toUpperCase()}>
        {concentration.status === "available" ? (
          <div className="metric-list">
            <Metric label="Largest holding" value={percent(concentration.largest_holding_weight as string)} />
            <Metric label="Top five holdings" value={percent(concentration.top_five_weight as string)} />
            <Metric label="Individual stocks" value={percent(concentration.stock_weight as string)} />
            <Metric label="ETFs" value={percent(concentration.etf_weight as string)} />
            <Metric label="Cash" value={percent(concentration.cash_weight as string)} />
            <Metric label="Missing data" value={percent(concentration.missing_data_pct as string)} />
          </div>
        ) : <MissingDataWarning reason={String(concentration.reason ?? "No portfolio exists.")} />}
        <SourceTimestamp source={concentration.source as string | null} asOf={concentration.as_of as string | null} status={String(concentration.missing_data_basis ?? "DETERMINISTIC")} />
      </DataPanel>
    </div>
  );
}

function Performance({ analytics }: { analytics: Analytics }) {
  const performance = analytics.performance;
  return (
    <div className="analytics-grid">
      <DataPanel title="Adjusted total return" meta="DISTRIBUTIONS INCLUDED">
        {performance.status === "available" ? (
          <div className="metric-list">
            <Metric label="Portfolio return" value={percent(performance.portfolio_return)} />
            <Metric label={performance.benchmark} value={percent(performance.benchmark_return)} />
            <Metric label="Difference" value={percent(performance.difference)} />
          </div>
        ) : <MissingDataWarning title={performance.label} reason={performance.reason ?? "Required evidence is unavailable."} />}
        <SourceTimestamp source={performance.source} asOf={performance.as_of} coverage={percent(performance.coverage_pct)} status={`${performance.currency} · ADJUSTED TOTAL RETURN ONLY`} />
      </DataPanel>
      <DataPanel title="Return periods" meta={`${performance.currency} · EXTERNAL FLOWS REQUIRED`}>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Period</th><th className="numeric">Portfolio</th><th className="numeric">Benchmark</th></tr></thead>
            <tbody>
              {performance.periods.length ? performance.periods.map((row) => <tr key={row.period}><td>{row.period}</td><td className="numeric">{percent(row.portfolio)}</td><td className="numeric">{percent(row.benchmark)}</td></tr>) : (
                <tr><td colSpan={3} className="unavailable-cell">INSUFFICIENT TRANSACTION HISTORY · current holdings are not backfilled</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </DataPanel>
    </div>
  );
}

function Risk({ analytics }: { analytics: Analytics }) {
  const risk = analytics.risk;
  const currency = analytics.currency_exposure;
  return (
    <div className="analytics-grid">
      <DataPanel title="Historical risk" meta="NOT A FORECAST">
        {risk.status === "available" ? (
          <div className="metric-list">
            <Metric label="Annualized volatility" value={percent(risk.annualized_volatility)} />
            <Metric label="Maximum drawdown" value={percent(risk.maximum_drawdown)} tone="negative" />
            <Metric label={`Beta vs. ${risk.benchmark}`} value={risk.beta ?? "NOT AVAILABLE"} />
            <Metric label="Correlation" value={risk.correlation ?? "NOT AVAILABLE"} />
          </div>
        ) : <MissingDataWarning title={risk.label} reason={risk.reason ?? "Aligned adjusted history is unavailable."} />}
        <p className="evidence-disclaimer">{risk.disclaimer || "Historical risk · not a forecast"}</p>
        <SourceTimestamp source={risk.source} asOf={risk.as_of} coverage={percent(risk.coverage_pct)} status={`${risk.measurement_period ?? "NO PERIOD"} · ${risk.observation_frequency ?? "NO FREQUENCY"}`} />
      </DataPanel>
      <DataPanel title="Currency exposure" meta="ECONOMIC EXPOSURE">
        {currency.status === "available" ? <div className="panel-body">{currency.categories.map((row) => <Meter key={row.currency} label={row.currency} value={Number(row.weight)} />)}</div> : <MissingDataWarning title={currency.label} reason={currency.reason ?? "Economic currency evidence is unavailable."} />}
        <div className="separate-evidence">
          <strong>TRADING CURRENCY · SHOWN SEPARATELY</strong>
          {currency.trading_currency.map((row) => <span key={row.currency}>{row.currency} {percent(row.weight)}</span>)}
        </div>
        <SourceTimestamp source={currency.source} asOf={currency.as_of} coverage={percent(currency.coverage_pct)} status="UNKNOWN REMAINS VISIBLE" />
      </DataPanel>
    </div>
  );
}

function EtfLookthrough({ analytics }: { analytics: Analytics }) {
  const data = analytics.etf_lookthrough;
  return (
    <>
      <DataPanel title="ETF holdings overlap" meta="ISSUER HOLDINGS ONLY">
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>ETF pair</th><th className="numeric">Overlap by weight</th><th>Largest duplicated holdings</th><th>Coverage</th><th>Issuer evidence date</th><th>Verification date</th></tr></thead>
            <tbody>
              {data.overlap.length ? data.overlap.map((row) => <tr key={row.pair}><td>{row.pair}</td><td className="numeric">{percent(row.overlap_by_weight)}</td><td>{row.largest_duplicated_holdings.join(", ")}</td><td>{percent(row.coverage_pct)}</td><td>{row.issuer_evidence_date}</td><td>{row.verification_date}</td></tr>) : <tr><td colSpan={6} className="unavailable-cell">NOT AVAILABLE · verified constituent holdings are not stored; overlap is not estimated</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="panel-warning">{data.warning}</div>
      </DataPanel>
      <div className="analytics-grid below-grid">
        <DataPanel title="Verified fee and allocation evidence" meta={`${percent(data.coverage_pct)} SECTOR COVERAGE`}>
          <div className="metric-list">
            <Metric label="Weighted portfolio MER" value={data.weighted_mer == null ? "NOT AVAILABLE" : percent(data.weighted_mer)} />
            <Metric label="ETF country allocation" value={data.country_allocation.length ? "AVAILABLE" : "NOT AVAILABLE"} />
            <Metric label="Supported issuer profiles" value={String(data.evidence.length)} />
          </div>
        </DataPanel>
        <DataPanel title="ETF evidence profiles" meta="NO BROAD AUTOMATIC SUPPORT CLAIM">
          <div className="table-wrap">
            <table className="data-table"><thead><tr><th>ETF</th><th>Issuer</th><th>Data as of</th><th>Verified</th><th>Coverage</th><th>Status</th><th>Source</th></tr></thead><tbody>
              {data.evidence.length ? data.evidence.map((row) => <tr key={row.symbol}><td className="symbol">{row.symbol}</td><td>{row.issuer ?? "UNKNOWN"}</td><td>{row.as_of ?? "MISSING"}</td><td>{row.verified_on ?? "MISSING"}</td><td>{percent(row.coverage_pct)}</td><td className={row.stale ? "warning" : row.stale === false ? "positive" : "negative"}>{row.stale ? "STALE" : row.stale === false ? "CURRENT" : "MISSING"}</td><td>{row.source_url ? <a href={row.source_url} target="_blank" rel="noreferrer">ISSUER SOURCE</a> : "MISSING"}</td></tr>) : <tr><td colSpan={7} className="unavailable-cell">NO SUPPORTED ETF EVIDENCE PROFILES</td></tr>}
            </tbody></table>
          </div>
        </DataPanel>
      </div>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="metric-row"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}
