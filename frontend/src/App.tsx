import { useCallback, useEffect, useState } from "react";
import { getMarketStrip } from "./api";
import { AppShell, TOP_TABS, type TopTab } from "./components/AppShell";
import { PortfolioApp } from "./portfolio/PortfolioApp";
import { CommandBar } from "./terminal/CommandBar";
import { MarketStrip } from "./terminal/MarketStrip";
import { TerminalPage } from "./terminal/TerminalPage";
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
  const tab = TOP_TABS.find((candidate) => candidate.toLowerCase() === first.toLowerCase())
    ?? TOP_TABS.find((candidate) => candidate === readStorage(TOP_TAB_KEY))
    ?? "Terminal";
  const symbol = (tab === "Terminal" && second ? second : readStorage(SYMBOL_KEY)) || "SPY";
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
    if (activeTab === "Terminal") {
      window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#terminal/${symbol}`);
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
    selectTab("Terminal");
  }

  return (
    <AppShell
      activeTab={activeTab}
      onTab={selectTab}
      search={<CommandBar onSubmit={openSymbol} />}
      strip={<MarketStrip items={strip} onOpen={openSymbol} />}
    >
      {activeTab === "Terminal" ? <TerminalPage symbol={symbol} onOpenSymbol={openSymbol} /> : <PortfolioApp />}
    </AppShell>
  );
}
