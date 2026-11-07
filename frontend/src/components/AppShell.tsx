import type { PropsWithChildren, ReactNode } from "react";
import type { DataOrigin } from "../types";

export const TOP_TABS = ["Research", "Portfolio"] as const;
export type TopTab = (typeof TOP_TABS)[number];

/** Portfolio detail views, each opened as a drawer over the holdings summary. */
export const PORTFOLIO_VIEWS = [
  "Holdings",
  "Activity",
  "Income",
  "Analytics",
  "Decisions",
  "Reviews",
  "Settings",
] as const;

export type PortfolioView = (typeof PORTFOLIO_VIEWS)[number];

export function originLabel(origin: DataOrigin | null | undefined): string {
  if (origin === "demo") return "Demo data · synthetic";
  if (origin === "manual") return "Manual portfolio";
  return "No portfolio";
}

export function AppShell({
  activeTab,
  onTab,
  search,
  strip,
  onMcp,
  onMacro,
  children,
}: PropsWithChildren<{
  activeTab: TopTab;
  onTab: (tab: TopTab) => void;
  search: ReactNode;
  strip: ReactNode;
  onMcp: () => void;
  onMacro: () => void;
}>) {
  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">IT</span>
          <h1>Investment Tracker</h1>
        </div>
        <div className="header-search">{search}</div>
        {strip}
        <button type="button" className="header-link macro-link" onClick={onMacro}>Macro</button>
        <button type="button" className="header-link" onClick={onMcp}>
          <span className="header-dot" aria-hidden="true" />MCP Server
        </button>
        <div className="top-tabs" role="tablist" aria-label="Main views">
          {TOP_TABS.map((tab) => (
            <button type="button" role="tab" key={tab} aria-selected={activeTab === tab} onClick={() => onTab(tab)}>
              {tab}
            </button>
          ))}
        </div>
      </header>
      <main className="workspace">{children}</main>
    </div>
  );
}

export function StatusBanner({
  error,
  notice,
}: {
  error: string | null;
  notice: string | null;
}) {
  return (
    <>
      {error && <div className="status-banner error" role="alert">ERROR · {error}</div>}
      {notice && <div className="status-banner notice" role="status">{notice}</div>}
    </>
  );
}
