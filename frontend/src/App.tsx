import { useCallback, useEffect, useRef, useState } from "react";
import {
  applySnapTradeSync,
  cancelSnapTradeSync,
  checkSnapTradeConnection,
  createReviewTrigger,
  createSnapTradePortal,
  deleteLocalBrokerageData,
  disconnectSnapTrade,
  generateReviewPack,
  getActivity,
  getAIReviews,
  getAnalytics,
  getHistory,
  getIncome,
  getJournal,
  getPendingSnapTradeSync,
  getPortfolio,
  getPriceCapabilities,
  getPrompts,
  getSectorAnalysis,
  getSnapTradeStatus,
  importAIReview,
  previewSnapTradeSync,
  refreshPrices,
  removePortfolioPosition,
  savePrompt,
  updateDecision,
  updateInstrumentSector,
  updateInvestmentProfile,
} from "./api";
import { AppShell, MAIN_TABS, StatusBanner, type MainTab } from "./components/AppShell";
import { SyncPreview } from "./components/SyncPreview";
import { ConfirmationDialog } from "./components/ui";
import { ActivityPage } from "./pages/ActivityPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DecisionsPage } from "./pages/DecisionsPage";
import { HoldingsPage } from "./pages/HoldingsPage";
import { IncomePage } from "./pages/IncomePage";
import { ResearchPage } from "./pages/ResearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import type {
  ActivityPayload,
  AIReview,
  Analytics,
  ClaudePrompt,
  HistoryPoint,
  Holding,
  IncomePayload,
  JournalPayload,
  Portfolio,
  PriceCapabilities,
  ReviewPack,
  ReviewPrivacy,
  SectorAnalysis,
  SnapTradeStatus,
  SnapTradeSyncPreview,
} from "./types";

const ACTIVE_TAB_KEY = "investment-tracker.active-tab.v1";
const PRIVACY_KEY = "investment-tracker.review-privacy.v1";

function initialTab(): MainTab {
  const hash = window.location.hash.replace("#", "");
  const stored = window.localStorage.getItem(ACTIVE_TAB_KEY) ?? "";
  return MAIN_TABS.find((tab) => tab.toLowerCase() === hash.toLowerCase())
    ?? MAIN_TABS.find((tab) => tab === stored)
    ?? "Dashboard";
}

function initialPrivacy(): ReviewPrivacy {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PRIVACY_KEY) ?? "null");
    if (stored && typeof stored === "object") {
      return {
        weights_only: stored.weights_only !== false,
        include_quantities: stored.include_quantities === true,
        include_dollar_values: stored.include_dollar_values === true,
        include_account_type: stored.include_account_type === true,
      };
    }
  } catch {
    // Invalid local preferences are safely restored.
  }
  return {
    weights_only: true,
    include_quantities: false,
    include_dollar_values: false,
    include_account_type: false,
  };
}

type Confirmation =
  | { kind: "delete-row"; holding: Holding }
  | { kind: "disconnect" }
  | { kind: "delete-brokerage-data" }
  | null;

export function App() {
  const [activeTab, setActiveTab] = useState<MainTab>(initialTab);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [sectors, setSectors] = useState<SectorAnalysis | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [activity, setActivity] = useState<ActivityPayload | null>(null);
  const [income, setIncome] = useState<IncomePayload | null>(null);
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  const [prompts, setPrompts] = useState<ClaudePrompt[]>([]);
  const [reviews, setReviews] = useState<AIReview[]>([]);
  const [snaptradeStatus, setSnaptradeStatus] = useState<SnapTradeStatus | null>(null);
  const [priceCapabilities, setPriceCapabilities] = useState<PriceCapabilities | null>(null);
  const [syncPreview, setSyncPreview] = useState<SnapTradeSyncPreview | null>(null);
  const [pack, setPack] = useState<ReviewPack | null>(null);
  const [privacy, setPrivacy] = useState<ReviewPrivacy>(initialPrivacy);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [syncConfirmed, setSyncConfirmed] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const automaticSyncAttempted = useRef(false);

  const load = useCallback(async () => {
    const [
      currentPortfolio,
      currentHistory,
      currentSectors,
      currentAnalytics,
      currentActivity,
      currentIncome,
      currentJournal,
      currentPrompts,
      currentReviews,
      currentStatus,
      currentCapabilities,
      pendingPreview,
    ] = await Promise.all([
      getPortfolio(), getHistory(), getSectorAnalysis(), getAnalytics(), getActivity(), getIncome(),
      getJournal(), getPrompts(), getAIReviews(), getSnapTradeStatus(), getPriceCapabilities(),
      getPendingSnapTradeSync(),
    ]);
    setPortfolio(currentPortfolio);
    setHistory(currentHistory);
    setSectors(currentSectors);
    setAnalytics(currentAnalytics);
    setActivity(currentActivity);
    setIncome(currentIncome);
    setJournal(currentJournal);
    setPrompts(currentPrompts);
    setReviews(currentReviews);
    setSnaptradeStatus(currentStatus);
    setPriceCapabilities(currentCapabilities);
    setSyncPreview(pendingPreview);
    if (!pendingPreview) setSyncConfirmed(false);
  }, []);

  useEffect(() => {
    async function initialize() {
      const returned = new URLSearchParams(window.location.search).get("snaptrade") === "connected";
      if (returned) {
        const clean = new URL(window.location.href);
        clean.searchParams.delete("snaptrade");
        window.history.replaceState({}, "", `${clean.pathname}${clean.search}${clean.hash}`);
        try {
          const checked = await checkSnapTradeConnection();
          setNotice(checked.connection_status === "connected_read_only"
            ? "SnapTrade connection confirmed. A holdings-and-activity preview will be prepared when eligible."
            : "SnapTrade returned. Check the reported connection state before reconnecting.");
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : "Unable to verify the SnapTrade connection");
        }
      }
      await load();
    }
    void initialize().catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load Investment Tracker"));
  }, [load]);

  const startSync = useCallback(async (automatic = false) => {
    if (busy || syncPreview) return;
    setBusy(true);
    if (!automatic) { setError(null); setNotice(null); }
    try {
      const preview = await previewSnapTradeSync();
      setSyncPreview(preview);
      setSyncConfirmed(false);
      if (!automatic) setNotice("Synchronization preview ready. Review holdings and completed activities before applying.");
    } catch (cause) {
      if (!automatic) setError(cause instanceof Error ? cause.message : "Unable to prepare synchronization preview");
    } finally {
      setBusy(false);
      void getSnapTradeStatus().then(setSnaptradeStatus).catch(() => undefined);
    }
  }, [busy, syncPreview]);

  useEffect(() => {
    if (automaticSyncAttempted.current
      || snaptradeStatus?.connection_status !== "connected_read_only"
      || !snaptradeStatus.sync_allowed
      || syncPreview) return;
    automaticSyncAttempted.current = true;
    void startSync(true);
  }, [snaptradeStatus, startSync, syncPreview]);

  useEffect(() => {
    const seconds = priceCapabilities?.automatic_refresh_seconds;
    if (!priceCapabilities?.automatic_refresh_supported || !seconds || seconds < 30 || seconds > 60 || !portfolio) return;
    const timer = window.setInterval(() => void refreshPrices().then(load).catch(() => undefined), seconds * 1000);
    return () => window.clearInterval(timer);
  }, [load, portfolio, priceCapabilities]);

  function navigate(tab: MainTab) {
    setActiveTab(tab);
    window.localStorage.setItem(ACTIVE_TAB_KEY, tab);
    window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#${tab.toLowerCase()}`);
  }

  function updatePrivacy(next: ReviewPrivacy) {
    const safe = next.weights_only ? { ...next, include_quantities: false, include_dollar_values: false } : next;
    setPrivacy(safe);
    window.localStorage.setItem(PRIVACY_KEY, JSON.stringify(safe));
  }

  async function run(action: () => Promise<void>, success?: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      if (success) setNotice(success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The local operation failed");
    } finally {
      setBusy(false);
    }
  }

  async function openPortal() {
    setBusy(true);
    setError(null);
    try {
      window.location.assign(await createSnapTradePortal());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open the SnapTrade portal");
      setBusy(false);
    }
  }

  async function applySync() {
    if (!syncPreview || !syncConfirmed) return;
    await run(async () => {
      await applySnapTradeSync(syncPreview.preview_id);
      setSyncPreview(null);
      setSyncConfirmed(false);
    }, "The reviewed holdings and activities were stored in a new immutable local snapshot.");
  }

  async function cancelSync() {
    if (syncPreview) await cancelSnapTradeSync(syncPreview.preview_id).catch(() => undefined);
    setSyncPreview(null);
    setSyncConfirmed(false);
  }

  async function confirmAction() {
    const target = confirmation;
    setConfirmation(null);
    if (!target) return;
    if (target.kind === "delete-row") {
      await run(() => removePortfolioPosition(target.holding.position_id), `${target.holding.canonical_symbol} was removed from a new local snapshot. No trade was placed.`);
    } else if (target.kind === "disconnect") {
      await run(disconnectSnapTrade, "Wealthsimple disconnection was requested. Local snapshots were preserved.");
    } else {
      await run(deleteLocalBrokerageData, "SnapTrade-derived local snapshots and normalized activities were deleted. Legacy snapshots were preserved.");
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
      case "Dashboard": return <DashboardPage portfolio={portfolio} sectors={sectors} analytics={analytics} journal={journal} income={income} onNavigate={navigate} />;
      case "Holdings": return <HoldingsPage portfolio={portfolio} sectors={sectors} journal={journal} busy={busy} onRefresh={() => void run(refreshPrices, "Independent market prices refreshed.")} onDelete={(holding) => setConfirmation({ kind: "delete-row", holding })} onSector={(id, sector) => void run(() => updateInstrumentSector(id, sector), "Sector classification saved.")} onDecision={(id, decision) => void run(() => updateDecision(id, decision, "Updated from the holdings worksheet"), "Decision recorded in history.")} />;
      case "Analytics": return <AnalyticsPage analytics={analytics} sectors={sectors} />;
      case "Income": return <IncomePage income={income} />;
      case "Activity": return <ActivityPage activity={activity} />;
      case "Decisions": return <DecisionsPage journal={journal} busy={busy} onDecision={(id, decision, reason = "Updated from the decision worksheet", disposition = null, reviewDue = null) => void run(() => updateDecision(id, decision, reason, disposition, reviewDue), "Decision recorded without changing any Claude review.")} onProfile={(id, profile) => void run(() => updateInvestmentProfile(id, profile), "Conviction and thesis saved locally.")} onTrigger={(id, trigger) => void run(() => createReviewTrigger(id, trigger), "Review trigger created. No order or external action was created.")} />;
      case "Research": return <ResearchPage portfolio={portfolio} journal={journal} prompts={prompts} reviews={reviews} privacy={privacy} onPrivacy={updatePrivacy} pack={pack} busy={busy} onPack={(...args) => void makePack(...args)} onReview={(review) => void run(() => importAIReview(review), "AI review stored separately from your decision.")} />;
      case "Settings": return <SettingsPage status={snaptradeStatus} priceCapabilities={priceCapabilities} history={history} privacy={privacy} prompts={prompts} busy={busy} previewOpen={Boolean(syncPreview)} onPrivacy={updatePrivacy} onConnect={() => void openPortal()} onCheck={() => void run(async () => { setSnaptradeStatus(await checkSnapTradeConnection()); }, "Connection status refreshed.")} onSync={() => void startSync()} onRefresh={() => void run(refreshPrices, "Independent market prices refreshed.")} onDisconnect={() => setConfirmation({ kind: "disconnect" })} onDeleteData={() => setConfirmation({ kind: "delete-brokerage-data" })} onSavePrompt={(prompt) => void run(async () => { await savePrompt(prompt); }, "Reusable Claude prompt saved locally.")} />;
    }
  })();

  const dialog = confirmation?.kind === "delete-row"
    ? { title: `Delete ${confirmation.holding.canonical_symbol} from the local snapshot?`, description: "This creates a new local portfolio snapshot without the selected row. It is not a Wealthsimple sale and never contacts SnapTrade or a brokerage.", label: "DELETE LOCAL ROW" }
    : confirmation?.kind === "disconnect"
      ? { title: "Disconnect Wealthsimple from SnapTrade?", description: "This stops future synchronization. Existing local snapshots and journal records remain available.", label: "DISCONNECT" }
      : { title: "Delete local brokerage data?", description: "This permanently deletes SnapTrade-derived local snapshots, normalized activities and sync metadata. Legacy non-SnapTrade snapshots are preserved.", label: "DELETE LOCAL DATA" };

  return (
    <AppShell activeTab={activeTab} onTab={navigate} holdingsAsOf={snaptradeStatus?.holdings_as_of ?? portfolio?.source_as_of ?? portfolio?.created_at ?? null} snaptradeStatus={snaptradeStatus}>
      <StatusBanner error={error} notice={notice} />
      {syncPreview && <SyncPreview preview={syncPreview} busy={busy} confirmed={syncConfirmed} onConfirmed={setSyncConfirmed} onApply={() => void applySync()} onCancel={() => void cancelSync()} />}
      {content}
      <ConfirmationDialog open={Boolean(confirmation)} title={dialog.title} description={dialog.description} confirmLabel={dialog.label} danger onCancel={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </AppShell>
  );
}
