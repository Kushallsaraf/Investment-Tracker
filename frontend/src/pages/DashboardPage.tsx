import { useState } from "react";
import { cad, decisionLabel, percent, signedCad, statusLabel, statusTone, timestamp } from "../lib/format";
import type { Analytics, IncomePayload, JournalPayload, Portfolio, SectorAnalysis } from "../types";
import { DataPanel, Donut, MissingDataWarning, SourceTimestamp, StatCell, ViewHeader } from "../components/ui";
import type { MainTab } from "../components/AppShell";

const EXPOSURE_COLORS: Record<string, string> = {
  "Canada equity": "#78a9dd",
  "United States": "#6cc6b0",
  International: "#b190dd",
  "Fixed income": "#d5aa64",
  Cash: "#5e6874",
  Unknown: "#3a424c",
};

function costSummary(portfolio: Portfolio) {
  let cost = 0;
  let covered = 0;
  for (const holding of portfolio.holdings) {
    const quantity = Number(holding.quantity);
    const average = Number(holding.average_cost);
    const conversion = holding.trading_currency === "CAD" ? 1 : Number(portfolio.fx?.rate);
    if ([quantity, average, conversion].every(Number.isFinite)) {
      cost += quantity * average * conversion;
      covered += 1;
    }
  }
  return { cost, coverage: portfolio.holdings.length ? covered / portfolio.holdings.length : 0 };
}

export function DashboardPage({
  portfolio,
  sectors,
  analytics,
  journal,
  income,
  onNavigate,
}: {
  portfolio: Portfolio | null;
  sectors: SectorAnalysis | null;
  analytics: Analytics | null;
  journal: JournalPayload | null;
  income: IncomePayload | null;
  onNavigate: (tab: MainTab) => void;
}) {
  const [period, setPeriod] = useState("1Y");
  if (!portfolio) {
    return (
      <>
        <ViewHeader title="Portfolio dashboard" subtitle="TFSA · CAD reporting" />
        <MissingDataWarning reason="No accepted portfolio snapshot exists. Connect or synchronize in Settings, review the preview, then apply it." />
      </>
    );
  }
  const cost = costSummary(portfolio);
  const gain = portfolio.holdings.reduce((sum, row) => {
    const value = Number(row.unrealized_gain_loss_cad);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
  const gainCoverage = portfolio.holdings.filter((row) => row.unrealized_gain_loss_cad != null).length;
  const gainPct = cost.cost > 0 ? gain / cost.cost : null;
  const decisionByInstrument = new Map(
    (journal?.entries ?? []).map((entry) => [entry.holding.instrument_id, entry.decision?.decision]),
  );
  const incomeCad = income?.received_by_currency.CAD;
  const hasNonCadIncome = Object.entries(income?.received_by_currency ?? {}).some(
    ([currency, value]) => currency !== "CAD" && Number(value) !== 0,
  );
  const exposure = analytics?.economic_exposure;
  const exposureSegments = (exposure?.categories ?? []).map((row) => ({
    label: row.name,
    value: Number(row.weight),
    color: EXPOSURE_COLORS[row.name] ?? EXPOSURE_COLORS.Unknown,
  }));
  const staleCount = portfolio.holdings.filter((row) => row.price_stale || !row.price).length;
  const newestQuote = [...portfolio.holdings]
    .map((row) => row.price_timestamp)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  const triggered = journal?.alerts.length ?? 0;
  return (
    <>
      <ViewHeader
        title="Portfolio dashboard"
        subtitle={`TFSA · ${portfolio.total_positions} holdings · CAD reporting`}
        asOf={portfolio.source_as_of ?? portfolio.created_at}
      />
      <section className="summary-strip" aria-label="Portfolio summary">
        <StatCell label="Market value" value={cad(portfolio.total_cad)} detail={`CAD · ${percent(portfolio.position_coverage_pct)} price coverage`} />
        <StatCell label="Total cost" value={cost.coverage ? cad(cost.cost) : "NOT AVAILABLE"} detail={`${percent(cost.coverage)} cost-basis coverage · latest FX`} />
        <StatCell label="Unrealized gain" value={gainCoverage ? signedCad(gain) : "NOT AVAILABLE"} detail={gainPct == null ? "Missing cost basis" : `${percent(gainPct)} · ${gainCoverage}/${portfolio.total_positions} holdings`} tone={gain >= 0 ? "positive" : "negative"} />
        <StatCell label="Today’s change" value="NOT AVAILABLE" detail="Previous-close data not stored" />
        <StatCell
          label="Annual income"
          value={income?.coverage.complete ? cad(incomeCad ?? "0") : incomeCad ? cad(incomeCad) : "NOT AVAILABLE"}
          detail={hasNonCadIncome ? "CAD portion only · activity-date FX unavailable" : income?.coverage.complete ? "Received · trailing 12 months" : "TTM activity coverage incomplete"}
        />
      </section>
      <section className="alert-strip" aria-label="Portfolio alerts">
        <div><strong>{triggered} review trigger{triggered === 1 ? "" : "s"} due</strong><span>{triggered ? journal?.alerts[0]?.message : "No active trigger alerts"}</span></div>
        <div><strong className={staleCount ? "warning" : "positive"}>{staleCount ? `${staleCount} missing or stale price${staleCount === 1 ? "" : "s"}` : "Price evidence available"}</strong><span>Newest quote · {timestamp(newestQuote)}</span></div>
        <div><strong className={Number(sectors?.etf_coverage_pct ?? 0) < 1 ? "warning" : "positive"}>ETF evidence coverage · {percent(sectors?.etf_coverage_pct)}</strong><span>{sectors?.evidence.length ?? 0} explicitly supported issuer profile{sectors?.evidence.length === 1 ? "" : "s"}</span></div>
      </section>
      <div className="two-panel-row">
        <DataPanel title="Economic exposure" meta={exposure?.etf_lookthrough_available ? "ETF LOOK-THROUGH ON" : "ETF LOOK-THROUGH UNAVAILABLE"}>
          {exposureSegments.length ? (
            <>
              <Donut
                segments={exposureSegments}
                label="Known portfolio economic exposure and unknown exposure"
                centerLabel={exposure?.etf_lookthrough_available ? "ETF look-through" : "Partial evidence"}
              />
              <div className="panel-warning">{exposure?.warning}</div>
              <SourceTimestamp source={exposure?.source} asOf={exposure?.as_of} coverage={percent(exposure?.coverage_pct)} status="PARTIAL" />
            </>
          ) : <MissingDataWarning reason="Economic exposure requires verified issuer and company evidence. Trading currency is not substituted." />}
        </DataPanel>
        <DataPanel
          title="Total-return performance"
          actions={<div className="period-controls">{["1M", "YTD", "1Y", "ALL"].map((value) => <button type="button" key={value} aria-pressed={period === value} onClick={() => setPeriod(value)}>{value}</button>)}</div>}
        >
          <MissingDataWarning
            title={analytics?.performance.label ?? "INSUFFICIENT DATA"}
            reason={analytics?.performance.reason ?? "Adjusted total-return history is unavailable."}
          />
          <SourceTimestamp source={analytics?.performance.source} asOf={analytics?.performance.as_of} coverage={percent(analytics?.performance.coverage_pct)} status={`PERIOD ${period} · DISTRIBUTIONS REQUIRED`} />
        </DataPanel>
      </div>
      <DataPanel title="Largest holdings" actions={<button className="action" type="button" onClick={() => onNavigate("Holdings")}>VIEW ALL HOLDINGS</button>}>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Holding</th><th>Type</th><th className="numeric">Market value</th><th className="numeric">Gain/loss</th><th className="numeric">Weight</th><th>My decision</th><th>Price status</th></tr></thead>
            <tbody>
              {portfolio.holdings.slice(0, 5).map((row) => (
                <tr key={row.position_id}>
                  <td className="symbol">{row.canonical_symbol}<small>{row.security_name}</small></td>
                  <td>{row.asset_type}</td>
                  <td className="numeric">{cad(row.market_value_cad)}</td>
                  <td className={`numeric ${Number(row.unrealized_gain_loss_cad) >= 0 ? "positive" : "negative"}`}>{signedCad(row.unrealized_gain_loss_cad)}</td>
                  <td className="numeric">{percent(row.portfolio_weight)}</td>
                  <td>{decisionLabel(decisionByInstrument.get(row.instrument_id))}</td>
                  <td className={statusTone(row)}>{statusLabel(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <SourceTimestamp source="Latest immutable local valuation snapshot" asOf={portfolio.created_at} coverage={percent(portfolio.position_coverage_pct)} status="HISTORICAL RISK NOT A FORECAST" />
      </DataPanel>
    </>
  );
}
