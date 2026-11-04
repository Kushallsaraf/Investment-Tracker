import { useCallback, useEffect, useState } from "react";
import {
  createActivity,
  createReviewTrigger,
  decideExitPlan,
  deleteActivity,
  deletePortfolioData,
  generateReviewPack,
  getActivity,
  getAIReviews,
  getAnalytics,
  getExitPlans,
  getHistory,
  getIncome,
  getJournal,
  getPortfolio,
  getPortfolioStatus,
  getPriceCapabilities,
  getPrompts,
  getSectorAnalysis,
  importAIReview,
  loadDemoPortfolio,
  refreshPrices,
  removePortfolioPosition,
  savePrompt,
  updateDecision,
  updateInstrumentSector,
  updateInvestmentProfile,
  upsertPosition,
} from "../api";
import { originLabel, PORTFOLIO_VIEWS, type PortfolioView, StatusBanner } from "../components/AppShell";
import { Drawer } from "../components/Drawer";
import { ConfirmationDialog, EmptyState } from "../components/ui";
import { decisionLabel, percent, signedUsd, statusLabel, timestamp, usd } from "../lib/format";
import { ActivityPage } from "../pages/ActivityPage";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { DecisionsPage } from "../pages/DecisionsPage";
import { HoldingsPage } from "../pages/HoldingsPage";
import { IncomePage } from "../pages/IncomePage";
import { ResearchPage } from "../pages/ResearchPage";
import { ReviewQueue } from "./ReviewQueue";
import { SettingsPage } from "../pages/SettingsPage";
import type {
  Activity,
  ActivityPayload,
  AIReview,
  Analytics,
  ClaudePrompt,
  ExitPlan,
  HistoryPoint,
  Holding,
  IncomePayload,
  JournalPayload,
  Portfolio,
  PortfolioStatus,
  PriceCapabilities,
  ReviewPack,
  ReviewPrivacy,
  SectorAnalysis,
} from "../types";

const PRIVACY_KEY = "investment-tracker.review-privacy.v2";

const SECTOR_PALETTE = ["#6fa8ff", "#2ec4b6", "#b39df2", "#e3b65c", "#ff8a80", "#8fc4e8", "#a3c47a", "#d49ac4", "#c9b48a", "#7fb8a8", "#9aa4d6", "#c78f6b"];
const FIXED_COLORS: Record<string, string> = { Cash: "#5c6068", Unknown: "#363a41" };
const WIDE_VIEWS = new Set<PortfolioView>(["Holdings", "Activity", "Analytics", "Decisions", "Reviews", "Settings"]);
const VIEW_TITLES: Record<PortfolioView, { title: string; subtitle: string }> = {
  Holdings: { title: "Edit holdings", subtitle: "Spreadsheet-style worksheet · every save creates a new local snapshot" },
  Activity: { title: "Activity", subtitle: "Buys, sells, dividends and cash movements in the local ledger" },
  Income: { title: "Income", subtitle: "Dividends and interest received over the last 12 months" },
  Analytics: { title: "Analytics", subtitle: "Performance, risk and ETF look-through, with missing data shown" },
  Decisions: { title: "Decisions and alerts", subtitle: "Your decisions, theses and review triggers" },
  Reviews: { title: "AI review packs", subtitle: "Sanitized Markdown you can paste into Claude" },
  Settings: { title: "Settings", subtitle: "Prices, privacy, demo data and saved prompts" },
};

function initialView(): PortfolioView | null {
  const hashView = window.location.hash.replace("#", "").split("/")[1] ?? "";
  // "Research" was the old name of the review-pack view.
  const wanted = hashView.toLowerCase() === "research" ? "reviews" : hashView.toLowerCase();
  return PORTFOLIO_VIEWS.find((view) => view.toLowerCase() === wanted) ?? null;
}

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

function initialPrivacy(): ReviewPrivacy {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PRIVACY_KEY) ?? "null");
    if (stored && typeof stored === "object") {
      return {
        weights_only: stored.weights_only !== false,
        include_quantities: stored.include_quantities === true,
        include_dollar_values: stored.include_dollar_values === true,
        include_account_name: stored.include_account_name === true,
      };
    }
  } catch {
    // Invalid local preferences are safely restored.
  }
  return {
    weights_only: true,
    include_quantities: false,
    include_dollar_values: false,
    include_account_name: false,
  };
}

type Confirmation =
  | { kind: "delete-row"; holding: Holding }
  | { kind: "delete-activity"; activity: Activity }
  | { kind: "load-demo" }
  | { kind: "delete-portfolio-data" }
  | null;

export function PortfolioApp({ onOpenSymbol }: { onOpenSymbol: (symbol: string) => void }) {
  const [activeTab, setActiveTab] = useState<PortfolioView | null>(initialView);
  const [selectedPosition, setSelectedPosition] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [status, setStatus] = useState<PortfolioStatus | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [sectors, setSectors] = useState<SectorAnalysis | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [activity, setActivity] = useState<ActivityPayload | null>(null);
  const [income, setIncome] = useState<IncomePayload | null>(null);
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  const [prompts, setPrompts] = useState<ClaudePrompt[]>([]);
  const [proposals, setProposals] = useState<ExitPlan[]>([]);
  const [reviews, setReviews] = useState<AIReview[]>([]);
  const [priceCapabilities, setPriceCapabilities] = useState<PriceCapabilities | null>(null);
  const [pack, setPack] = useState<ReviewPack | null>(null);
  const [privacy, setPrivacy] = useState<ReviewPrivacy>(initialPrivacy);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);

  const load = useCallback(async () => {
    const [
      currentPortfolio,
      currentStatus,
      currentHistory,
      currentSectors,
      currentAnalytics,
      currentActivity,
      currentIncome,
      currentJournal,
      currentPrompts,
      currentReviews,
      currentCapabilities,
      currentProposals,
    ] = await Promise.all([
      getPortfolio(), getPortfolioStatus(), getHistory(), getSectorAnalysis(), getAnalytics(), getActivity(),
      getIncome(), getJournal(), getPrompts(), getAIReviews(), getPriceCapabilities(), getExitPlans("PROPOSED"),
    ]);
    setPortfolio(currentPortfolio);
    setStatus(currentStatus);
    setHistory(currentHistory);
    setSectors(currentSectors);
    setAnalytics(currentAnalytics);
    setActivity(currentActivity);
    setIncome(currentIncome);
    setJournal(currentJournal);
    setPrompts(currentPrompts);
    setReviews(currentReviews);
    setPriceCapabilities(currentCapabilities);
    setProposals(currentProposals);
  }, []);

  useEffect(() => {
    void load().catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load Investment Tracker"));
  }, [load]);

  useEffect(() => {
    const seconds = priceCapabilities?.automatic_refresh_seconds;
    if (!priceCapabilities?.automatic_refresh_supported || !seconds || seconds < 30 || seconds > 60 || !portfolio) return;
    const timer = window.setInterval(() => void refreshPrices().then(load).catch(() => undefined), seconds * 1000);
    return () => window.clearInterval(timer);
  }, [load, portfolio, priceCapabilities]);

  function navigate(view: PortfolioView | null) {
    setActiveTab(view);
    window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#portfolio${view ? `/${view.toLowerCase()}` : ""}`);
  }

  function updatePrivacy(next: ReviewPrivacy) {
    const safe = next.weights_only ? { ...next, include_quantities: false, include_dollar_values: false } : next;
    setPrivacy(safe);
    window.localStorage.setItem(PRIVACY_KEY, JSON.stringify(safe));
  }

  async function run(action: () => Promise<void>, success?: string): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      if (success) setNotice(success);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The local operation failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function confirmAction() {
    const target = confirmation;
    setConfirmation(null);
    if (!target) return;
    if (target.kind === "delete-row") {
      await run(() => removePortfolioPosition(target.holding.position_id), `${target.holding.canonical_symbol} was removed from a new local snapshot. No trade was placed.`);
    } else if (target.kind === "delete-activity") {
      await run(() => deleteActivity(target.activity.id), "The activity was deleted from the local ledger.");
    } else if (target.kind === "load-demo") {
      await run(loadDemoPortfolio, "The synthetic demo portfolio was loaded. Prices are fetched live.");
    } else {
      await run(deletePortfolioData, "Local holdings, valuations and activities were deleted. Journal records were kept.");
    }
  }

  async function makePack(instrumentId: string, promptId: string, triggerId: string | null, save: boolean) {
    setBusy(true); setError(null);
    try {
      const nextPack = await generateReviewPack(instrumentId, promptId, triggerId, privacy, save);
      setPack(nextPack);
      if (save) {
        const blob = new Blob([nextPack.markdown], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${nextPack.symbol}-claude-review-${new Date().toISOString().slice(0, 10)}.md`;
        anchor.click();
        URL.revokeObjectURL(url);
        setNotice("Sanitized Markdown exported locally. Nothing was sent to Claude.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to generate review pack");
    } finally { setBusy(false); }
  }

  const content = (() => {
    switch (activeTab) {
      case null: return null;
      case "Holdings": return <HoldingsPage portfolio={portfolio} sectors={sectors} journal={journal} busy={busy} onRefresh={() => void run(refreshPrices, "Independent market prices refreshed.")} onUpsert={(position) => run(async () => { await upsertPosition(position); }, `${position.symbol.toUpperCase()} saved in a new local snapshot.`)} onDelete={(holding) => setConfirmation({ kind: "delete-row", holding })} onSector={(id, sector) => void run(() => updateInstrumentSector(id, sector), "Sector classification saved.")} onDecision={(id, decision) => void run(() => updateDecision(id, decision, "Updated from the holdings worksheet"), "Decision recorded in history.")} />;
      case "Analytics": return <AnalyticsPage analytics={analytics} sectors={sectors} />;
      case "Income": return <IncomePage income={income} />;
      case "Activity": return <ActivityPage activity={activity} busy={busy} onCreate={(input) => run(() => createActivity(input), "Activity recorded in the local ledger.")} onDelete={(row) => setConfirmation({ kind: "delete-activity", activity: row })} />;
      case "Decisions": return <><ReviewQueue alerts={journal?.alerts ?? []} proposals={proposals} busy={busy} onOpen={(symbol) => { navigate(null); onOpenSymbol(symbol); }} onDecide={(plan, decision) => void run(async () => { await decideExitPlan(plan.id, decision); }, decision === "accept" ? `${plan.symbol} exit plan accepted. Review alerts were created; no order was placed.` : `${plan.symbol} exit plan rejected and kept in its history.`)} /><DecisionsPage journal={journal} busy={busy} onDecision={(id, decision, reason = "Updated from the decision worksheet", disposition = null, reviewDue = null) => void run(() => updateDecision(id, decision, reason, disposition, reviewDue), "Decision recorded without changing any Claude review.")} onProfile={(id, profile) => void run(() => updateInvestmentProfile(id, profile), "Conviction and thesis saved locally.")} onTrigger={(id, trigger) => void run(() => createReviewTrigger(id, trigger), "Review trigger created. No order or external action was created.")} /></>;
      case "Reviews": return <ResearchPage portfolio={portfolio} journal={journal} prompts={prompts} reviews={reviews} privacy={privacy} onPrivacy={updatePrivacy} pack={pack} busy={busy} onPack={(...args) => void makePack(...args)} onReview={(review) => void run(() => importAIReview(review), "AI review stored separately from your decision.")} />;
      case "Settings": return <SettingsPage status={status} priceCapabilities={priceCapabilities} history={history} privacy={privacy} prompts={prompts} busy={busy} onPrivacy={updatePrivacy} onRefresh={() => void run(refreshPrices, "Independent market prices refreshed.")} onLoadDemo={() => setConfirmation({ kind: "load-demo" })} onDeleteData={() => setConfirmation({ kind: "delete-portfolio-data" })} onSavePrompt={(prompt) => void run(async () => { await savePrompt(prompt); }, "Reusable Claude prompt saved locally.")} />;
    }
  })();

  const dialog = confirmation?.kind === "delete-row"
    ? { title: `Delete ${confirmation.holding.canonical_symbol} from the local snapshot?`, description: "This creates a new local portfolio snapshot without the selected row. It is not a sale and never contacts a brokerage.", label: "DELETE LOCAL ROW" }
    : confirmation?.kind === "delete-activity"
      ? { title: `Delete this ${confirmation.activity.activity_type.toLowerCase()} activity?`, description: "The activity is removed from the local ledger. Holdings are not changed.", label: "DELETE ACTIVITY" }
      : confirmation?.kind === "load-demo"
        ? { title: "Load the synthetic demo portfolio?", description: "This replaces any existing demo holdings and demo activities with illustrative US stocks and ETFs. Manual portfolios are never overwritten.", label: "LOAD DEMO" }
        : { title: "Delete local portfolio data?", description: "This permanently deletes all local holdings snapshots, valuations, quotes and activities. Decisions, theses, triggers and AI reviews are kept.", label: "DELETE LOCAL DATA" };

  const decisionByInstrument = new Map((journal?.entries ?? []).map((entry) => [entry.holding.instrument_id, entry.decision?.decision]));
  const selected = portfolio?.holdings.find((row) => row.position_id === selectedPosition) ?? null;
  const alerts = (journal?.alerts.length ?? 0) + proposals.length;

  return (
    <>
      <StatusBanner error={error} notice={notice} />
      {portfolio ? (
        <PortfolioSummary
          portfolio={portfolio}
          sectors={sectors}
          income={income}
          alerts={alerts}
          origin={status?.data_origin}
          decisions={decisionByInstrument}
          onView={navigate}
          onSelect={setSelectedPosition}
        />
      ) : (
        <EmptyState title="No portfolio yet">
          <p>Add positions by hand, or load a synthetic demo portfolio to explore.</p>
          <div className="drawer-actions" style={{ justifyContent: "center" }}>
            <button className="action primary" type="button" onClick={() => navigate("Holdings")}>Add positions</button>
            <button className="action" type="button" disabled={busy} onClick={() => setConfirmation({ kind: "load-demo" })}>Load demo portfolio</button>
          </div>
        </EmptyState>
      )}
      <Drawer
        open={activeTab !== null}
        eyebrow="Portfolio"
        title={activeTab ? VIEW_TITLES[activeTab].title : ""}
        subtitle={activeTab ? VIEW_TITLES[activeTab].subtitle : undefined}
        wide={activeTab !== null && WIDE_VIEWS.has(activeTab)}
        onClose={() => navigate(null)}
      >
        {content}
      </Drawer>
      <Drawer
        open={selected !== null}
        eyebrow={selected?.canonical_symbol}
        title={selected?.security_name ?? ""}
        subtitle={selected ? `${selected.asset_type} · ${selected.exchange} · ${selected.account_name}` : undefined}
        onClose={() => setSelectedPosition(null)}
      >
        {selected && (
          <PositionDetail
            holding={selected}
            decision={decisionByInstrument.get(selected.instrument_id)}
            onResearch={() => { setSelectedPosition(null); onOpenSymbol(selected.canonical_symbol); }}
            onEdit={() => { setSelectedPosition(null); navigate("Holdings"); }}
          />
        )}
      </Drawer>
      <ConfirmationDialog open={Boolean(confirmation)} title={dialog.title} description={dialog.description} confirmLabel={dialog.label} danger={confirmation?.kind !== "load-demo"} onCancel={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </>
  );
}

function PortfolioSummary({
  portfolio,
  sectors,
  income,
  alerts,
  origin,
  decisions,
  onView,
  onSelect,
}: {
  portfolio: Portfolio;
  sectors: SectorAnalysis | null;
  income: IncomePayload | null;
  alerts: number;
  origin: PortfolioStatus["data_origin"] | undefined;
  decisions: Map<string, string | undefined>;
  onView: (view: PortfolioView) => void;
  onSelect: (positionId: string) => void;
}) {
  const cost = costSummary(portfolio);
  const segments = (sectors?.categories ?? []).map((row, index) => ({
    label: row.sector,
    weight: Number(row.portfolio_weight),
    color: FIXED_COLORS[row.sector] ?? SECTOR_PALETTE[index % SECTOR_PALETTE.length],
  })).filter((row) => row.weight > 0);
  const staleCount = portfolio.holdings.filter((row) => row.price_stale || !row.price).length;
  return (
    <>
      <section className="portfolio-head" aria-label="Portfolio summary">
        <div>
          <h2>Portfolio value <span className={`origin-badge ${origin === "manual" ? "" : "warning"}`.trim()}>{originLabel(origin)}</span></h2>
          <div className="portfolio-value">
            <strong>{usd(portfolio.total_value)}</strong>
            {cost.gainCount > 0 && <span className={cost.gain >= 0 ? "positive" : "negative"}>{signedUsd(cost.gain)}{cost.gainPct == null ? "" : ` · ${cost.gain >= 0 ? "+" : ""}${percent(cost.gainPct)}`}</span>}
            <small>{portfolio.total_positions} holdings · as of {timestamp(portfolio.snapshot_created_at)}</small>
          </div>
        </div>
        <div className="portfolio-tools">
          <button className="action" type="button" onClick={() => onView("Activity")}>Activity</button>
          <button className="action" type="button" onClick={() => onView("Income")}>Income</button>
          <button className="action" type="button" onClick={() => onView("Analytics")}>Analytics</button>
          <button className="action" type="button" onClick={() => onView("Decisions")}>Alerts · {alerts}</button>
          <button className="action" type="button" onClick={() => onView("Reviews")}>AI review packs</button>
          <button className="action" type="button" aria-label="Settings" onClick={() => onView("Settings")}>Settings</button>
          <button className="action primary" type="button" onClick={() => onView("Holdings")}>Edit holdings</button>
        </div>
      </section>
      <section className="summary-strip four" aria-label="Key figures">
        <div className="stat-cell"><span className="compact-label">Invested cost</span><strong>{cost.coverage ? usd(cost.cost) : "Not available"}</strong><small>{percent(cost.coverage)} of holdings have a cost basis</small></div>
        <div className="stat-cell"><span className="compact-label">Unrealized gain</span><strong className={cost.gainCount ? (cost.gain >= 0 ? "positive" : "negative") : ""}>{cost.gainCount ? signedUsd(cost.gain) : "Not available"}</strong><small>{cost.gainCount}/{cost.securityCount} securities</small></div>
        <div className="stat-cell"><span className="compact-label">Income · 12 months</span><strong>{income?.coverage.count ? usd(income.received) : "Not available"}</strong><small>{income?.coverage.count ? "Received, from your ledger" : "No activities recorded"}</small></div>
        <div className="stat-cell"><span className="compact-label">Price coverage</span><strong className={staleCount ? "warning" : ""}>{percent(portfolio.position_coverage_pct)}</strong><small>{staleCount ? `${staleCount} missing or stale` : "All prices current"}</small></div>
      </section>
      {segments.length > 0 && (
        <section className="allocation" aria-label="Sector allocation">
          <div className="allocation-bar" role="img" aria-label={`Sector allocation: ${segments.map((row) => `${row.label} ${percent(row.weight)}`).join(", ")}`}>
            {segments.map((row) => <i key={row.label} style={{ width: `${row.weight * 100}%`, background: row.color }} />)}
          </div>
          <div className="allocation-legend">
            {segments.map((row) => <span key={row.label}><i style={{ background: row.color }} />{row.label} <b>{percent(row.weight)}</b></span>)}
          </div>
        </section>
      )}
      <section className="holding-list" aria-label="Holdings">
        <div className="holding-row header" aria-hidden="true">
          <span>Holding</span><span className="num">Value</span><span className="num">Gain/loss</span><span className="num hide-narrow">Weight</span><span className="num hide-narrow">Price</span><span className="num hide-narrow">My decision</span>
        </div>
        {portfolio.holdings.map((row) => {
          const gain = row.unrealized_gain_loss == null ? null : Number(row.unrealized_gain_loss);
          const stale = Boolean(row.price_stale || !row.price);
          return (
            <button type="button" key={row.position_id} className="holding-row" aria-label={`${row.canonical_symbol} details`} onClick={() => onSelect(row.position_id)}>
              <span className="holding-sym"><strong>{row.canonical_symbol}</strong><small>{row.security_name}</small></span>
              <span className="num">{usd(row.market_value)}</span>
              <span className={`num ${gain == null ? "" : gain >= 0 ? "positive" : "negative"}`.trim()}>{gain == null ? "—" : signedUsd(gain)}</span>
              <span className="num hide-narrow">{percent(row.portfolio_weight)}</span>
              <span className={`num hide-narrow ${stale ? "warning" : ""}`.trim()} title={statusLabel(row)}>{row.price ? usd(row.price) : "No price"}</span>
              <span className="holding-decision hide-narrow">{row.asset_type === "CASH" ? "Cash" : decisionLabel(decisions.get(row.instrument_id))}</span>
            </button>
          );
        })}
      </section>
    </>
  );
}

function PositionDetail({
  holding,
  decision,
  onResearch,
  onEdit,
}: {
  holding: Holding;
  decision: string | undefined;
  onResearch: () => void;
  onEdit: () => void;
}) {
  const facts: Array<[string, string, string?]> = [
    ["Market value", usd(holding.market_value)],
    ["Gain/loss", holding.unrealized_gain_loss == null ? "—" : signedUsd(holding.unrealized_gain_loss), holding.unrealized_gain_loss == null ? undefined : Number(holding.unrealized_gain_loss) >= 0 ? "positive" : "negative"],
    ["Quantity", holding.quantity],
    ["Average cost", holding.average_cost == null ? "—" : usd(holding.average_cost)],
    ["Last price", holding.price ? usd(holding.price) : "No price"],
    ["Weight", percent(holding.portfolio_weight)],
    ["Sector", holding.manual_sector ?? "Unclassified"],
    ["My decision", holding.asset_type === "CASH" ? "—" : decisionLabel(decision)],
  ];
  return (
    <>
      <div className="position-facts">
        {facts.map(([label, value, factTone]) => <div key={label}><span>{label}</span><strong className={factTone}>{value}</strong></div>)}
      </div>
      <p className="panel-note" style={{ margin: 0 }}>{statusLabel(holding)} · price as of {timestamp(holding.price_timestamp)}{holding.price_source ? ` · ${holding.price_source}` : ""}</p>
      <div className="drawer-actions">
        {holding.asset_type !== "CASH" && <button className="action primary" type="button" onClick={onResearch}>Open in Research</button>}
        <button className="action" type="button" onClick={onEdit}>Edit in worksheet</button>
      </div>
    </>
  );
}
