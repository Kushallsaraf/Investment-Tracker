import { useCallback, useEffect, useState } from "react";
import { getMarketStrip } from "./api";
import { AppShell, TOP_TABS, type TopTab } from "./components/AppShell";
import { PortfolioApp } from "./portfolio/PortfolioApp";
import { CommandBar } from "./research/CommandBar";
import { MarketStrip } from "./research/MarketStrip";
import { ResearchView } from "./research/ResearchView";
import type { StripItem } from "./types";

const TOP_TAB_KEY = "investment-tracker.top-tab.v1";
const SYMBOL_KEY = "investment-tracker.terminal-symbol.v1";
const STRIP_REFRESH_MS = 5 * 60 * 1000;

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Preferences are a convenience; the app works without storage.
  }
}

function initialRoute(): { tab: TopTab; symbol: string } {
  const [first = "", second = ""] = window.location.hash.replace("#", "").split("/");
  // "#terminal/SYM" links from before the rename still open Research.
  const hashTab = first.toLowerCase() === "terminal" ? "research" : first.toLowerCase();
  const tab = TOP_TABS.find((candidate) => candidate.toLowerCase() === hashTab)
    ?? TOP_TABS.find((candidate) => candidate === readStorage(TOP_TAB_KEY))
    ?? "Research";
  const symbol = (tab === "Research" && second ? second : readStorage(SYMBOL_KEY)) || "SPY";
  return { tab, symbol: symbol.toUpperCase() };
}

export function App() {
  const [route] = useState(initialRoute);
  const [activeTab, setActiveTab] = useState<TopTab>(route.tab);
  const [symbol, setSymbol] = useState(route.symbol);
  const [strip, setStrip] = useState<StripItem[] | null>(null);

  const loadStrip = useCallback(() => {
    void getMarketStrip().then(setStrip).catch(() => setStrip([]));
  }, []);

  useEffect(() => {
    loadStrip();
    const timer = window.setInterval(loadStrip, STRIP_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadStrip]);

  useEffect(() => {
    if (activeTab === "Research") {
      window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#research/${symbol}`);
    } else if (!window.location.hash.startsWith("#portfolio")) {
      window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#portfolio`);
    }
  }, [activeTab, symbol]);

  function selectTab(tab: TopTab) {
    setActiveTab(tab);
    writeStorage(TOP_TAB_KEY, tab);
  }

  function openSymbol(next: string) {
    // Class shares are canonical with a dot (BRK.B); accept the hyphen or slash spellings too.
    const normalized = next.trim().toUpperCase().replace(/[-/]/g, ".");
    if (!normalized) return;
    setSymbol(normalized);
    writeStorage(SYMBOL_KEY, normalized);
    selectTab("Research");
  }

  return (
    <AppShell
      activeTab={activeTab}
      onTab={selectTab}
      search={<CommandBar onSubmit={openSymbol} />}
      strip={<MarketStrip items={strip} onOpen={openSymbol} />}
    >
      {activeTab === "Research" ? <ResearchView symbol={symbol} onOpenSymbol={openSymbol} /> : <PortfolioApp onOpenSymbol={openSymbol} />}
    </AppShell>
  );
}
