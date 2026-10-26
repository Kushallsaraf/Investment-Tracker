import { cad, timestamp } from "../lib/format";
import type { IncomePayload } from "../types";
import { DataPanel, EmptyState, Meter, MissingDataWarning, SourceTimestamp, StatCell, ViewHeader } from "../components/ui";

function currencySummary(values: Record<string, string>): string {
  const entries = Object.entries(values).filter(([, value]) => Number(value) !== 0);
  if (!entries.length) return "NOT AVAILABLE";
  if (entries.length === 1 && entries[0][0] === "CAD") return cad(entries[0][1]);
  return entries.map(([currency, value]) => `${Number(value).toLocaleString("en-CA", { maximumFractionDigits: 2 })} ${currency}`).join(" · ");
}

export function IncomePage({ income }: { income: IncomePayload | null }) {
  const cadByHolding = (income?.income_by_holding ?? []).map((row) => ({ symbol: row.symbol, value: Number(row.amounts.CAD ?? 0) }));
  const totalCad = cadByHolding.reduce((sum, row) => sum + row.value, 0);
  return (
    <>
      <ViewHeader title="Income" subtitle="Completed dividends, ETF distributions and interest · gross and net evidence separated where available" asOf={income?.source_as_of} />
      <section className="summary-strip four">
        <StatCell label="Received · trailing 12 months" value={currencySummary(income?.received_by_currency ?? {})} detail={income?.coverage.complete ? "All returned pages · lifetime coverage not guaranteed" : "Returned-page coverage incomplete"} />
        <StatCell label="Forward annual estimate" value="NOT AVAILABLE" detail="Estimate evidence not stored · not guaranteed" />
        <StatCell label="Portfolio yield" value="NOT AVAILABLE" detail="Forward income unavailable" />
        <StatCell label="Withholding tax" value={currencySummary(income?.withholding_tax_by_currency ?? {})} detail="Trailing 12 months · source currencies" />
      </section>
      <div className="two-panel-row">
        <DataPanel title="Upcoming distributions" meta="ANNOUNCED OR ESTIMATED STATUS REQUIRED">
          <MissingDataWarning reason="No reliable announced distribution calendar is connected. Dates and amounts are not predicted." />
          <SourceTimestamp source={null} asOf={null} status="NO ESTIMATES GENERATED" />
        </DataPanel>
        <DataPanel title="Income concentration by holding" meta="TRAILING 12 MONTHS · CAD ACTIVITIES">
          {!income ? <EmptyState title="NO ACTIVITY DATA">Synchronize completed brokerage activities.</EmptyState> : totalCad > 0 ? (
            <div className="panel-body">
              {cadByHolding.filter((row) => row.value > 0).sort((a, b) => b.value - a.value).map((row) => <Meter key={row.symbol} label={`${row.symbol} · ${cad(row.value)}`} value={row.value / totalCad} />)}
            </div>
          ) : <MissingDataWarning reason="No CAD dividend, distribution, or interest cash activities exist in the covered period." />}
          <SourceTimestamp source={income?.source} asOf={income?.source_as_of} status={income?.coverage.complete ? "ALL RETURNED PAGES · LIFETIME COVERAGE NOT GUARANTEED" : "INCOMPLETE RETURNED-PAGE COVERAGE"} />
        </DataPanel>
      </div>
      {income?.warnings.length ? <DataPanel title="Income data warnings" meta={`${income.warnings.length} NOTICE${income.warnings.length === 1 ? "" : "S"}`}><ul className="warning-list">{income.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul><SourceTimestamp source={income.source} asOf={income.source_as_of} coverage={`${timestamp(income.coverage.start)} — ${timestamp(income.coverage.end)}`} status="DAILY / CACHED" /></DataPanel> : null}
    </>
  );
}
