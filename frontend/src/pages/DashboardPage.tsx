import { useState } from "react";
import { decisionLabel, percent, signedUsd, statusLabel, statusTone, timestamp, usd } from "../lib/format";
import type { Analytics, IncomePayload, JournalPayload, Portfolio, SectorAnalysis } from "../types";
import { DataPanel, Donut, MissingDataWarning, SourceTimestamp, StatCell, ViewHeader } from "../components/ui";
import type { MainTab } from "../components/AppShell";

const SECTOR_PALETTE = ["#78a9dd", "#6cc6b0", "#b190dd", "#d5aa64", "#e08a8a", "#8fc4e8", "#a3c47a", "#d49ac4", "#c9b48a", "#7fb8a8", "#9aa4d6", "#c78f6b"];
const FIXED_COLORS: Record<string, string> = { Cash: "#5e6874", Unknown: "#3a424c" };

// Cash has no cost basis or gain, so only securities count toward cost and gain coverage.
function costSummary(portfolio: Portfolio) {
  const securities = portfolio.holdings.filter((holding) => holding.asset_type !== "CASH");
  let cost = 0;
  let covered = 0;
  let gain = 0;
  let gainBasis = 0;
  let gainCount = 0;
  for (const holding of securities) {
    const quantity = Number(holding.quantity);
    const average = Number(holding.average_cost);
    if (holding.average_cost == null || ![quantity, average].every(Number.isFinite)) continue;
    cost += quantity * average;
    covered += 1;
    const unrealized = Number(holding.unrealized_gain_loss);
    if (holding.unrealized_gain_loss != null && Number.isFinite(unrealized)) {
      gain += unrealized;
      gainBasis += quantity * average;
      gainCount += 1;
    }
  }
  return {
    cost,
    coverage: securities.length ? covered / securities.length : 0,
    gain,
    gainPct: gainBasis > 0 ? gain / gainBasis : null,
    gainCount,
    securityCount: securities.length,
  };
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
        <ViewHeader title="Portfolio dashboard" subtitle="US portfolio · USD reporting" />
        <MissingDataWarning reason="No portfolio exists yet. Add positions on the Holdings tab, or load the synthetic demo portfolio in Settings." />
      </>
    );
  }
  const cost = costSummary(portfolio);
  const decisionByInstrument = new Map(
    (journal?.entries ?? []).map((entry) => [entry.holding.instrument_id, entry.decision?.decision]),
  );
  const sectorSegments = (sectors?.categories ?? []).map((row, index) => ({
    label: row.sector,
    value: Number(row.portfolio_weight),
    color: FIXED_COLORS[row.sector] ?? SECTOR_PALETTE[index % SECTOR_PALETTE.length],
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
        subtitle={`${portfolio.data_origin === "demo" ? "Synthetic demo" : "Manual"} portfolio · ${portfolio.total_positions} holdings · USD reporting`}
        asOf={portfolio.snapshot_created_at}
      />
      <section className="summary-strip" aria-label="Portfolio summary">
        <StatCell label="Market value" value={usd(portfolio.total_value)} detail={`USD · ${percent(portfolio.position_coverage_pct)} price coverage`} />
        <StatCell label="Invested cost" value={cost.coverage ? usd(cost.cost) : "NOT AVAILABLE"} detail={`${percent(cost.coverage)} cost-basis coverage · excludes cash`} />
        <StatCell label="Unrealized gain" value={cost.gainCount ? signedUsd(cost.gain) : "NOT AVAILABLE"} detail={cost.gainPct == null ? "Missing cost basis" : `${percent(cost.gainPct)} · ${cost.gainCount}/${cost.securityCount} securities`} tone={cost.gain >= 0 ? "positive" : "negative"} />
        <StatCell label="Today’s change" value="NOT AVAILABLE" detail="Previous-close data not stored" />
        <StatCell
          label="Annual income"
          value={income?.coverage.count ? usd(income.received) : "NOT AVAILABLE"}
          detail={income?.coverage.count ? "Received · trailing 12 months · ledger" : "No activities recorded"}
        />
      </section>
      <section className="alert-strip" aria-label="Portfolio alerts">
        <div><strong>{triggered} review trigger{triggered === 1 ? "" : "s"} due</strong><span>{triggered ? journal?.alerts[0]?.message : "No active trigger alerts"}</span></div>
        <div><strong className={staleCount ? "warning" : "positive"}>{staleCount ? `${staleCount} missing or stale price${staleCount === 1 ? "" : "s"}` : "Price evidence available"}</strong><span>Newest quote · {timestamp(newestQuote)}</span></div>
        <div><strong className={Number(sectors?.etf_coverage_pct ?? 0) < 1 ? "warning" : "positive"}>ETF evidence coverage · {percent(sectors?.etf_coverage_pct)}</strong><span>{sectors?.evidence.length ?? 0} explicitly supported issuer profile{sectors?.evidence.length === 1 ? "" : "s"}</span></div>
      </section>
      <div className="two-panel-row">
        <DataPanel title="Sector allocation" meta={`${percent(sectors?.coverage_pct)} KNOWN`}>
          {sectorSegments.length ? (
            <>
              <Donut segments={sectorSegments} label="Portfolio sector allocation, including unknown exposure" centerLabel="Sectors" />
              <SourceTimestamp source="User classifications and supported issuer profiles" asOf={sectors?.calculated_at} coverage={percent(sectors?.coverage_pct)} status="UNKNOWN REMAINS VISIBLE" />
            </>
          ) : <MissingDataWarning reason="No valued sector allocation is available. Classify stocks on the Holdings tab." />}
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
                  <td className="numeric">{usd(row.market_value)}</td>
                  <td className={`numeric ${Number(row.unrealized_gain_loss) >= 0 ? "positive" : "negative"}`}>{row.unrealized_gain_loss == null ? "—" : signedUsd(row.unrealized_gain_loss)}</td>
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
