import type { PropsWithChildren, ReactNode } from "react";
import type { DataOrigin } from "../types";

export const TOP_TABS = ["Terminal", "Portfolio"] as const;
export type TopTab = (typeof TOP_TABS)[number];

export const PORTFOLIO_VIEWS = [
  "Overview",
  "Holdings",
  "Analytics",
  "Income",
  "Activity",
  "Decisions",
  "Research",
  "Settings",
] as const;

export type PortfolioView = (typeof PORTFOLIO_VIEWS)[number];

export function originLabel(origin: DataOrigin | null | undefined): string {
  if (origin === "demo") return "DEMO DATA · SYNTHETIC";
  if (origin === "manual") return "MANUAL PORTFOLIO";
  return "NO PORTFOLIO";
}

export function AppShell({
  activeTab,
  onTab,
  search,
  strip,
  children,
}: PropsWithChildren<{
  activeTab: TopTab;
  onTab: (tab: TopTab) => void;
  search: ReactNode;
  strip: ReactNode;
}>) {
  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="top-line">
          <div className="brand">
            <span className="brand-mark">IT</span>
            <div>
              <h1>Investment Tracker</h1>
              <p>US markets · daily data</p>
            </div>
          </div>
          <div className="header-search">{search}</div>
          <nav aria-label="Investment Tracker sections">
            <div className="top-tabs" role="tablist" aria-label="Main views">
              {TOP_TABS.map((tab) => (
                <button type="button" role="tab" key={tab} aria-selected={activeTab === tab} onClick={() => onTab(tab)}>
                  {tab}
                </button>
              ))}
            </div>
          </nav>
        </div>
        {strip}
      </header>
      <main className="workspace">{children}</main>
      <footer className="global-footer">
        Research only · No orders · No brokerage credentials · Daily, delayed data · Missing data shown explicitly
      </footer>
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
