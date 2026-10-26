import type { PropsWithChildren } from "react";
import { timestamp } from "../lib/format";
import type { DataOrigin } from "../types";

export const MAIN_TABS = [
  "Dashboard",
  "Holdings",
  "Analytics",
  "Income",
  "Activity",
  "Decisions",
  "Research",
  "Settings",
] as const;

export type MainTab = (typeof MAIN_TABS)[number];

export function originLabel(origin: DataOrigin | null | undefined): string {
  if (origin === "demo") return "DEMO DATA · SYNTHETIC";
  if (origin === "manual") return "MANUAL PORTFOLIO";
  return "NO PORTFOLIO";
}

export function AppShell({
  activeTab,
  onTab,
  holdingsAsOf,
  dataOrigin,
  children,
}: PropsWithChildren<{
  activeTab: MainTab;
  onTab: (tab: MainTab) => void;
  holdingsAsOf: string | null;
  dataOrigin: DataOrigin | null;
}>) {
  const originTone = dataOrigin === "manual" ? "positive" : "warning";
  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="top-line">
          <div className="brand">
            <span className="brand-mark">IT</span>
            <div>
              <h1>Investment Tracker</h1>
              <p>US portfolio · USD reporting</p>
            </div>
          </div>
          <div className="header-meta">
            <span>Holdings as of {timestamp(holdingsAsOf)}</span>
            <strong className={originTone}>{originLabel(dataOrigin)}</strong>
          </div>
        </div>
        <nav aria-label="Investment Tracker sections">
          <div className="main-navigation" role="tablist" aria-label="Main views">
            {MAIN_TABS.map((tab) => (
              <button
                type="button"
                role="tab"
                key={tab}
                aria-selected={activeTab === tab}
                onClick={() => onTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </nav>
      </header>
      <main className="workspace">{children}</main>
      <footer className="global-footer">
        Research only · No orders · No brokerage credentials · Exact timestamps · Missing data shown explicitly
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
