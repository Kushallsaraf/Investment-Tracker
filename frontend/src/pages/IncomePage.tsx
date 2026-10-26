import { dateOnly, usd } from "../lib/format";
import type { IncomePayload } from "../types";
import { DataPanel, EmptyState, Meter, MissingDataWarning, SourceTimestamp, StatCell, ViewHeader } from "../components/ui";

export function IncomePage({ income }: { income: IncomePayload | null }) {
  const byHolding = (income?.income_by_holding ?? [])
    .map((row) => ({ symbol: row.symbol, value: Number(row.amount) }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value);
  const total = byHolding.reduce((sum, row) => sum + row.value, 0);
  const recorded = Boolean(income?.coverage.count);
  const coverage = recorded ? `${dateOnly(income?.coverage.start)} — ${dateOnly(income?.coverage.end)}` : "NO ACTIVITIES";
  return (
    <>
      <ViewHeader title="Income" subtitle="Dividends and interest from the local activity ledger · gross and withholding tax separated" asOf={income?.period_end} />
      <section className="summary-strip four">
        <StatCell label="Received · trailing 12 months" value={recorded ? usd(income?.received) : "NOT AVAILABLE"} detail="Dividends and interest recorded in the ledger" />
        <StatCell label="Forward annual estimate" value="NOT AVAILABLE" detail="Estimate evidence not stored · not guaranteed" />
        <StatCell label="Portfolio yield" value="NOT AVAILABLE" detail="Forward income unavailable" />
        <StatCell label="Withholding tax" value={recorded ? usd(income?.withholding_tax) : "NOT AVAILABLE"} detail="Trailing 12 months" />
      </section>
      <div className="two-panel-row">
        <DataPanel title="Upcoming dividends" meta="ANNOUNCED OR ESTIMATED STATUS REQUIRED">
          <MissingDataWarning reason="No reliable announced dividend calendar is connected. Dates and amounts are not predicted." />
          <SourceTimestamp source={null} asOf={null} status="NO ESTIMATES GENERATED" />
        </DataPanel>
        <DataPanel title="Income concentration by holding" meta="TRAILING 12 MONTHS · USD">
          {!income ? <EmptyState title="NO ACTIVITY DATA">Record dividends and interest on the Activity tab.</EmptyState> : total > 0 ? (
            <div className="panel-body">
              {byHolding.map((row) => <Meter key={row.symbol} label={`${row.symbol} · ${usd(row.value)}`} value={row.value / total} />)}
            </div>
          ) : <MissingDataWarning reason="No dividend or interest activities exist in the trailing 12 months." />}
          <SourceTimestamp source={income?.source} asOf={income?.coverage.end} coverage={coverage} status="LEDGER ONLY" />
        </DataPanel>
      </div>
      {income?.warnings.length ? <DataPanel title="Income data notices" meta={`${income.warnings.length} NOTICE${income.warnings.length === 1 ? "" : "S"}`}><ul className="warning-list">{income.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></DataPanel> : null}
    </>
  );
}
