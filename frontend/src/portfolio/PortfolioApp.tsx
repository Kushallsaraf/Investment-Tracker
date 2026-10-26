import { useCallback, useEffect, useState } from "react";
import {
  createActivity,
  createReviewTrigger,
  deleteActivity,
  deletePortfolioData,
  generateReviewPack,
  getActivity,
  getAIReviews,
  getAnalytics,
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
import { ConfirmationDialog } from "../components/ui";
import { ActivityPage } from "../pages/ActivityPage";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DecisionsPage } from "../pages/DecisionsPage";
import { HoldingsPage } from "../pages/HoldingsPage";
import { IncomePage } from "../pages/IncomePage";
import { ResearchPage } from "../pages/ResearchPage";
import { SettingsPage } from "../pages/SettingsPage";
import type {
  Activity,
  ActivityPayload,
  AIReview,
  Analytics,
  ClaudePrompt,
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

const ACTIVE_VIEW_KEY = "investment-tracker.portfolio-view.v1";
const PRIVACY_KEY = "investment-tracker.review-privacy.v2";

function initialView(): PortfolioView {
  const hashView = window.location.hash.replace("#", "").split("/")[1] ?? "";
  const stored = window.localStorage.getItem(ACTIVE_VIEW_KEY) ?? "";
  return PORTFOLIO_VIEWS.find((view) => view.toLowerCase() === hashView.toLowerCase())
    ?? PORTFOLIO_VIEWS.find((view) => view === stored)
    ?? "Overview";
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

export function PortfolioApp() {
  const [activeTab, setActiveTab] = useState<PortfolioView>(initialView);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [status, setStatus] = useState<PortfolioStatus | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [sectors, setSectors] = useState<SectorAnalysis | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [activity, setActivity] = useState<ActivityPayload | null>(null);
  const [income, setIncome] = useState<IncomePayload | null>(null);
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  const [prompts, setPrompts] = useState<ClaudePrompt[]>([]);
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
    ] = await Promise.all([
      getPortfolio(), getPortfolioStatus(), getHistory(), getSectorAnalysis(), getAnalytics(), getActivity(),
      getIncome(), getJournal(), getPrompts(), getAIReviews(), getPriceCapabilities(),
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

  function navigate(view: PortfolioView) {
    setActiveTab(view);
    window.localStorage.setItem(ACTIVE_VIEW_KEY, view);
    window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#portfolio/${view.toLowerCase()}`);
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
      case "Overview": return <DashboardPage portfolio={portfolio} sectors={sectors} analytics={analytics} journal={journal} income={income} onNavigate={navigate} />;
      case "Holdings": return <HoldingsPage portfolio={portfolio} sectors={sectors} journal={journal} busy={busy} onRefresh={() => void run(refreshPrices, "Independent market prices refreshed.")} onUpsert={(position) => run(async () => { await upsertPosition(position); }, `${position.symbol.toUpperCase()} saved in a new local snapshot.`)} onDelete={(holding) => setConfirmation({ kind: "delete-row", holding })} onSector={(id, sector) => void run(() => updateInstrumentSector(id, sector), "Sector classification saved.")} onDecision={(id, decision) => void run(() => updateDecision(id, decision, "Updated from the holdings worksheet"), "Decision recorded in history.")} />;
      case "Analytics": return <AnalyticsPage analytics={analytics} sectors={sectors} />;
      case "Income": return <IncomePage income={income} />;
      case "Activity": return <ActivityPage activity={activity} busy={busy} onCreate={(input) => run(() => createActivity(input), "Activity recorded in the local ledger.")} onDelete={(row) => setConfirmation({ kind: "delete-activity", activity: row })} />;
      case "Decisions": return <DecisionsPage journal={journal} busy={busy} onDecision={(id, decision, reason = "Updated from the decision worksheet", disposition = null, reviewDue = null) => void run(() => updateDecision(id, decision, reason, disposition, reviewDue), "Decision recorded without changing any Claude review.")} onProfile={(id, profile) => void run(() => updateInvestmentProfile(id, profile), "Conviction and thesis saved locally.")} onTrigger={(id, trigger) => void run(() => createReviewTrigger(id, trigger), "Review trigger created. No order or external action was created.")} />;
      case "Research": return <ResearchPage portfolio={portfolio} journal={journal} prompts={prompts} reviews={reviews} privacy={privacy} onPrivacy={updatePrivacy} pack={pack} busy={busy} onPack={(...args) => void makePack(...args)} onReview={(review) => void run(() => importAIReview(review), "AI review stored separately from your decision.")} />;
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

  return (
    <>
      <StatusBanner error={error} notice={notice} />
      <div className="sub-bar">
        <div className="main-navigation" role="tablist" aria-label="Portfolio views">
          {PORTFOLIO_VIEWS.map((view) => (
            <button type="button" role="tab" key={view} aria-selected={activeTab === view} onClick={() => navigate(view)}>{view}</button>
          ))}
        </div>
        <strong className={`origin-badge ${status?.data_origin === "manual" ? "positive" : "warning"}`}>{originLabel(status?.data_origin)}</strong>
      </div>
      {content}
      <ConfirmationDialog open={Boolean(confirmation)} title={dialog.title} description={dialog.description} confirmLabel={dialog.label} danger={confirmation?.kind !== "load-demo"} onCancel={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </>
  );
}
